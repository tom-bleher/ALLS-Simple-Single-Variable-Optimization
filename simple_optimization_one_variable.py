import os
import cv2
import numpy as np
from ftplib import FTP
import shutil
import random
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from pyqtgraph.Qt import QtCore, QtWidgets
import sys 

"""
This is a simple optimization method which follows the increase
in count for a single variable in constant steps
"""

# this is the txt file the code adjusts and uploads 
MIRROR_TXT_PATH = r'dm_parameters.txt'

# open and read the txt file and read the initial values
with open(MIRROR_TXT_PATH, 'r') as file:
    content = file.read()
values = list(map(int, content.split()))

class ImageHandler(FileSystemEventHandler):
    def __init__(self, optimize_count_callback):
        super().__init__()
        self.optimize_count_callback = optimize_count_callback

    def on_created(self, event):
        if not event.is_directory:
            self.optimize_count_callback([event.src_path])

class BetatronApplication(QtWidgets.QApplication):
    def __init__(self, *args, **kwargs):
        super(BetatronApplication, self).__init__(*args, **kwargs)

        # establish connection via ftp with dm computer for the first time progra is ran
        # ip, windows user and password of deformable mirror computer
        self.ftp = FTP()
        self.ftp.connect(host="192.168.200.3")
        self.ftp.login(user="Utilisateur", passwd="alls")

        # initialize optimization variables
        self.single_img_mean_count = 0
        self.mean_count_per_image_group  = 0
        self.delta_count = 0

        # for how many images should the mean be taken for
        self.image_group = 2 

        # initialize optimization tracking variables
        self.image_groups_processed = 0
        self.images_processed = 0
        self.image_group_count_sum = 0  

        # grab the initial focus by the first value that was written in the txt file
        self.initial_focus = values[0]
        self.new_focus = 0
        
        # step size, in what step jumps should the program adjust the focus
        self.step_size = 1
        
        # initial direction guess for optimization 
        self.direction = random.choice([-1, +1])
        
        # set count change tolerance under which the program will consider the case optimized 
        self.count_change_tolerance = 10
        
        # initialize lists to keep track of optimization process
        self.count_history = []
        self.focus_history = []
        self.delta_count_history = []
        self.record_count_history = []
        self.min_delta_count_history = []

        # define global and local bounds for the optimization 
        self.lower_bound = max(self.initial_focus - 20, -200)
        self.upper_bound = min(self.initial_focus + 20, 200)

        # image path (should match to path specified in SpinView)
        self.IMG_PATH = r'images'

        # define the list of image files
        self.image_files = []
                
        # setup tracking for new images
        self.waiting_for_images_printed = False
        self.new_image_tracker()

        self.image_handler = ImageHandler(self.optimize_count)
        self.file_observer = Observer()
        self.file_observer.schedule(self.image_handler, path=self.IMG_PATH, recursive=False)
        self.file_observer.start()
    
    # method to track new incoming images in directory
    def new_image_tracker(self):
        
        # print that the program is waiting for images once
        if not self.waiting_for_images_printed:
            print("Waiting for images ...")
            self.waiting_for_images_printed = True
        
        # define a list to store the paths of new files
        self.new_files = [] 
        
        # iterate over each filename in the IMG_PATH directory
        for filename in os.listdir(self.IMG_PATH):
            # check if the filename ends with '.tiff'
            if filename.endswith('.tiff'):
                # add the file's path to the new_files list
                self.new_files.append(os.path.join(self.IMG_PATH, filename))

        if self.new_files:
            self.image_files = self.new_files

    # method used to send the new values to the deformable mirror computer via FTP
    def upload_files_to_ftp(self):

        mirror_files = [os.path.basename(MIRROR_TXT_PATH)]

        # try to send the file via ftp connection
        try:
            local_files = os.listdir(mirror_files)
            for file_name in local_files:
                local_MIRROR_TXT_PATH = os.path.join(mirror_files, file_name)
                if os.path.isfile(local_MIRROR_TXT_PATH):
                    copy_path = os.path.join(mirror_files, f'copy_{file_name}')
                    shutil.copy(local_MIRROR_TXT_PATH, copy_path)

                    with open(copy_path, 'rb') as local_file:
                        self.ftp.storbinary(f'STOR {file_name}', local_file)

                    os.remove(copy_path)
                    print(f"Uploaded: {file_name}")
        
        except Exception as e:
            print(f"Error: {e}")

    # method to calculate count (by its brightness proxy)
    def calc_count_per_image(self, image_path):
        
        # read the image in 16 bit
        original_image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
        
        # apply median blur on image
        median_blured_image = cv2.medianBlur(original_image, 5)
        
        # calculate mean brightness of blured image
        self.single_img_mean_count = median_blured_image.mean()
        
        # return the count (brightness of image)
        return self.single_img_mean_count

    # main optimization block consisting of logical statmants which follow the increase direction
    def optimize_count(self, new_images):

        self.new_image_tracker() 
        new_images = [image_path for image_path in new_images if os.path.exists(image_path)]
        new_images.sort(key=os.path.getctime)
        
        # loop over every new image
        for image_path in new_images:
                        
            # get the image's brightness using the dedicated function
            self.single_img_mean_count = self.calc_count_per_image(image_path)
            
            # sum the brightness for the specified number of images for which the mean will be taken
            self.image_group_count_sum += self.single_img_mean_count
            
            # keep track of the times the program ran (number of images we processed)
            self.images_processed += 1
            
            # conditional to check if the desired numbers of images to mean was processed
            if self.images_processed % self.image_group == 0:
                
                # take the mean count for the number of images set
                self.mean_count_per_image_group = np.mean(self.single_img_mean_count)
                
                # append to count_history list to keep track of count through the optimization process
                self.count_history.append(self.mean_count_per_image_group)

                # update count for 'image_group' processed 
                self.image_groups_processed += 1
                
                # if we are in the first time where the algorithm needs to adjust the value
                if self.image_groups_processed == 1:
                    print('-------------')       
                    print(f"initial focus: {values[0]}")
                    
                    # add initial focus to list (even though we already got the count for it)
                    self.focus_history.append(self.initial_focus)  
                    
                    # our first run is our first count peak
                    self.record_count_history.append(self.count_history[-1])
                    
                    # try random direction
                    self.new_focus = self.initial_focus + self.step_size * self.direction  
                    
                    # update new focus
                    self.focus_history.append(self.new_focus)
                    
                    # overwrite the txt file to the latest focus value
                    values[0] = self.focus_history[-1]
                    
                    print(f"first image, my initial direction is {self.direction}") 

                # if we are in the second time where the algorithm needs to make an adjustment decision
                elif self.image_groups_processed == 2: 
                    
                    # if the new brightness is larger than our previous record
                    if (self.count_history[-1] > self.record_count_history[-1]):
                        
                        # this the new peak count
                        self.record_count_history.append(self.count_history[-1]) 

                        # recalculate delta_count for new peak
                        delta_count = np.abs((self.count_history[-1] - self.count_history[-2]))
                        self.delta_count_history.append(delta_count) # add to respective list

                        # the first run is our closest to the current peak
                        self.min_delta_count_history.append(self.delta_count_history[-1]) 
                        
                        # continue in direction which led to count increase
                        self.new_focus = self.new_focus + self.step_size * self.direction 

                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print("New count record")

                    # if the new brightness is not larger, this wasn't the right direction
                    else: 
                        # recalculate delta_count for new peak
                        delta_count = np.abs((self.count_history[-1] - self.count_history[-2]))
                        self.delta_count_history.append(delta_count) # add to respective list           

                        # this is the current closest to the peak count
                        self.min_delta_count_history.append(self.delta_count_history[-1])

                        # switch direction
                        self.new_focus = self.new_focus + self.step_size * self.direction * -1 
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print("This is no good, switching direction")

                # on the third occurrence and forward we have enough data to start optimization
                else: 
                    # compare to record count
                    delta_count = np.abs((self.count_history[-1] - self.count_history[-2]))
                    self.delta_count_history.append(delta_count)
                    
                    # if latest count is larger than the previous record
                    if self.count_history[-1] > self.record_count_history[-1]:
                        # this is the new current peak count
                        self.record_count_history.append(self.count_history[-1]) 
                        
                        # continue in this direction
                        self.new_focus = self.new_focus + self.step_size * self.direction
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print("New count record")
                    
                    # we're close enough to the optimized value, stop adjusting focus value
                    elif np.abs((self.count_history[-1] - self.count_history[-2])) <= self.count_change_tolerance:
                        self.image_group_count_sum = 0
                        self.mean_count_per_image_group  = 0
                        self.single_img_mean_count = 0
                        print("I'm close to the peak count, not changing focus")

                    # we're closer than before to the record so continue in this direction
                    elif self.delta_count_history and self.min_delta_count_history and (np.abs(self.delta_count_history[-1]) < np.abs(self.min_delta_count_history[-1])):
                        # this is the new closest to the peak count
                        self.min_delta_count_history.append(self.delta_count_history[-1])  
                        self.new_focus = self.new_focus + self.step_size * self.direction
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        # update new focus
                        self.focus_history.append(self.new_focus)  
                        values[0] = self.focus_history[-1]
                        print(f"Let's continue in this direction")

                    else:  # we're not closer than before, let's move to the other direction instead
                        self.new_focus = self.new_focus + self.step_size * self.direction * -1
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print("This is no good, switching direction")
                
                # after the algorithm adjusted the value and wrote it to the txt, send new txt to deformable mirror computer
                # self.upload_files_to_ftp() 
                      
                # print the latest mean count (helps track system)
                print(f"Mean count for last {self.image_group} images: {self.count_history[-1]}")
                
                # print the current focus which resulted in the brightness above
                print(f"Current focus: {self.focus_history[-1]}")  
                print('-------------')

                # write new value to txt file
                with open(MIRROR_TXT_PATH, 'w') as file:
                    file.write(str(self.focus_history[-1]))

                # reset all variables for the next optimization round 
                self.image_group_count_sum = 0
                self.mean_count_per_image_group  = 0
                self.single_img_mean_count = 0

                QtCore.QCoreApplication.processEvents()

if __name__ == "__main__":
    app = BetatronApplication([])
    win = QtWidgets.QMainWindow()
    sys.exit(app.exec_())