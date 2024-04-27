import os
import cv2
import numpy as np
from ftplib import FTP
import shutil
import time
import random
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pyqtgraph.Qt import QtCore, QtWidgets
import sys 

# this is the txt file the code adjusts and uploads 
MIRROR_FILE_PATH = r'dm_parameters.txt'

with open(MIRROR_FILE_PATH, 'r') as file:
    content = file.read()
values = list(map(int, content.split()))
# print("Content read from file:", content)
# print("Values after conversion:", values)
initial_focus = values[0]

class ImageHandler(FileSystemEventHandler):
    def __init__(self, process_images_callback):
        super().__init__()
        self.process_images_callback = process_images_callback

    def on_created(self, event):
        if not event.is_directory:
            self.process_images_callback([event.src_path])

class BetatronApplication(QtWidgets.QApplication):
    def __init__(self, *args, **kwargs):
        super(BetatronApplication, self).__init__(*args, **kwargs)

        # ip, windows user and password of deformable mirror computer
        self.host = "192.168.200.3"
        self.user = "Utilisateur"
        self.password = "alls"

        self.img_mean_count = 0
        self.mean_count_per_n_images  = 0
        self.count_diff = 0
        self.n_images = 2
        self.n_images_run_count = 0
        self.run_count = 0
        self.n_images_count_sum = 0  

        self.initial_focus = values[0]
        self.new_focus = 0
        self.step = 1
        self.direction = random.choice([-1, +1])
        self.tolerance = 0.001

        self.count_history = []
        self.func_history = []
        self.focus_history = []
        self.count_diff_history = []
        self.record_count_history = []
        self.min_count_diff_history = []

        self.lower_bound = max(self.initial_focus - 20, -200)
        self.upper_bound = min(self.initial_focus + 20, 200)

        # image path (should correspond to SpinView)
        self.IMG_PATH = r'images'
        self.image_files = [os.path.join(self.IMG_PATH, filename) for filename in os.listdir(self.IMG_PATH) if filename.endswith('.tiff') and os.path.isfile(os.path.join(self.IMG_PATH, filename))]

        self.printed_message = False
        self.initialize_image_files()

        self.image_handler = ImageHandler(self.process_images)
        self.file_observer = Observer()
        self.file_observer.schedule(self.image_handler, path=self.IMG_PATH, recursive=False)
        self.file_observer.start()


    def initialize_image_files(self):
        if not self.printed_message:
            print("Waiting for images ...")
            self.printed_message = True

        new_files = [os.path.join(self.IMG_PATH, filename) for filename in os.listdir(self.IMG_PATH) if filename.endswith('.tiff') and os.path.isfile(os.path.join(self.IMG_PATH, filename))]

        if new_files:
            self.image_files = new_files

    def upload_files_to_ftp(self):
        ftp = FTP()
        ftp.connect(host=self.host)
        ftp.login(user=self.user, passwd=self.password)

        base_directory = 'Server'

        mirror_files = [os.path.basename(MIRROR_FILE_PATH)]

        try:
            local_files = os.listdir(mirror_files)
            for file_name in local_files:
                local_MIRROR_FILE_PATH = os.path.join(mirror_files, file_name)
                if os.path.isfile(local_MIRROR_FILE_PATH):

                    copy_path = os.path.join(mirror_files, f'copy_{file_name}')
                    shutil.copy(local_MIRROR_FILE_PATH, copy_path)

                    with open(copy_path, 'rb') as local_file:
                        ftp.storbinary(f'STOR {file_name}', local_file)

                    os.remove(copy_path)
                    print(f"Uploaded: {file_name}")
        except Exception as e:
            print(f"Error: {e}")

    def calc_xray_count(self, image_path):
        original_image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
        median_filtered_image = cv2.medianBlur(original_image, 5)
        self.img_mean_count = median_filtered_image.mean()

        return self.img_mean_count

    def process_images(self, new_images):

        self.initialize_image_files() 
        new_images = [image_path for image_path in new_images if os.path.exists(image_path)]
        new_images.sort(key=os.path.getctime)
        
        for image_path in new_images:
            relative_path = os.path.relpath(image_path, self.IMG_PATH)
            self.img_mean_count = self.calc_xray_count(image_path)
            self.n_images_count_sum += self.img_mean_count
            self.run_count += 1

            if self.run_count % self.n_images == 0:
                self.mean_count_per_n_images = np.mean(self.img_mean_count)
                self.count_history.append(self.mean_count_per_n_images)

                self.n_images_run_count += 1

                if self.n_images_run_count == 1:
                    print('-------------')       
                    print(f"initial focus: {values[0]}")
                    self.focus_history.append(self.initial_focus)  # add initial focus to list (even though we already got the count for it)
                    self.record_count_history.append(self.count_history[-1]) # our first run is our first count peak

                    self.new_focus = self.initial_focus + self.step * self.direction  # try the random direction
                    self.focus_history.append(self.new_focus)  # update new focus
                    values[0] = self.focus_history[-1]
                    print(f"first image, my initial direction is {self.direction}") 

                elif self.n_images_run_count == 2: 
                    
                    if (self.count_history[-1] > self.record_count_history[-1]):
                        self.record_count_history.append(self.count_history[-1])  # this the new peak count
 
                        count_diff = (self.count_history[-2] - self.record_count_history[-1])/(self.record_count_history[-1]) # recalculate count_diff for new peak
                        self.count_diff_history.append(count_diff)   

                        self.min_count_diff_history.append(self.count_diff_history[-1]) # the first run is our closest to the current peak
                        
                        self.new_focus = self.new_focus + self.step * self.direction # continue in direction which led to count increase

                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print(f"new record count")

                    else: # this wasn't the right direction
                        count_diff = (self.count_history[-1] - self.record_count_history[-1])/(self.record_count_history[-1]) # recalculate count_diff for new peak
                        self.count_diff_history.append(count_diff)                           
                        self.min_count_diff_history.append(self.count_diff_history[-1])  # this is the current closest to the peak count

                        self.new_focus = self.new_focus + self.step * self.direction * -1 # let's switch direction
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print("this is no good, switching direction")

                else: # now we have enough data start optimization
                    count_diff = (self.count_history[-1] - self.record_count_history[-1])/(self.record_count_history[-1]) # compare to record count
                    self.count_diff_history.append(count_diff)

                    if self.count_history[-1] > self.record_count_history[-1]:
                        self.record_count_history.append(self.count_history[-1])  # this is the new current peak count
                        # continue this direction
                        self.new_focus = self.new_focus + self.step * self.direction
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print(f"new record count")

                    elif self.count_diff_history and self.min_count_diff_history and (np.abs(self.count_diff_history[-1]) < np.abs(self.min_count_diff_history[-1])):
                        self.min_count_diff_history.append(self.count_diff_history[-1])  # this is the new closest to the peak count
                        self.new_focus = self.new_focus + self.step * self.direction
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)  # update new focus
                        values[0] = self.focus_history[-1]
                        print(f"let's continue this direction")

                    elif np.abs((self.count_history[-1] - self.record_count_history[-1])/(self.record_count_history[-1])) <= self.tolerance:
                        self.n_images_count_sum = 0
                        self.mean_count_per_n_images  = 0
                        self.img_mean_count = 0
                        print("I'm close to the peak count, not changing focus")
                        # we're close enough to the optimized value, let's stop changing the focus

                    else:  # we're not closer than before, let's move to the other direction instead
                        self.new_focus = self.new_focus + self.step * self.direction * -1
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print("this is no good, switching direction")

                # self.upload_files_to_ftp() # send new txt file to deformable mirror computer
                        
                print(f"mean_count_per_last_{self.n_images}_images {self.count_history[-1]}, current focus {self.focus_history[-1]}")  
                # print(f"{relative_path}, {self.count_history[-1]}, current focus {self.focus_history[-1]}")  
                print('-------------')

                self.n_images_count_sum = 0
                self.mean_count_per_n_images  = 0
                self.img_mean_count = 0

                QtCore.QCoreApplication.processEvents()

if __name__ == "__main__":
    app = BetatronApplication([])
    win = QtWidgets.QMainWindow()
    sys.exit(app.exec_())