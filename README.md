
### Project description
What does the code do?

- Program is ran
- Code waits for new images to appear in specified path
- Once a new Image is detected it's processed for its mean brightness
- The code continues until we have enough images to average (`self.n_images`)
- The code takes an initial guess (+1 or -1 to focus variable)
- The code compares the new parameter count against the initial parameter count
- If the resulting count is more, we continue following the direction; else, switch direction.
- Repeat until count is optimized 

### Code setup
##### Camera triggering and capture
We utilize a physical pulse generator (from master clock or photodiode) for the pulse generation to synchronize the camera triggering to laser. 

- Open the SpinView program
- Connect camera to triggering Stanford box and computer
- Adjust region of interest and bit depth to `16 bit`
- Switch `trigger mode` to on
- Click on record function 
- Set format to `.tiff` and recording mode to `Streaming`
- Select directory for the code to access 

##### Install imports
The following libraries are used for the projects, ensure you have installed the necessary libraries before proceeding.

```python
import os 
import cv2 # needs to be installed 
import numpy as np # needs to be installed 
from ftplib import FTP
import shutil
import time
import random
from watchdog.observers import Observer # needs to be installed 
from watchdog.events import FileSystemEventHandler # needs to be installed 
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets # needs to be installed 
import pyqtgraph as pg # needs to be installed 
import sys
```

##### Hard-coded paths
The code includes a number of hard coded paths, before proceeding adjust them accordingly to your setup.

```python
# computer near chamber
MIRROR_FILE_PATH = r'mirror_command/mirror_change.txt' # this is the txt file the code writes to
self.IMG_PATH = r'C:\Users\blehe\Desktop\Betatron\images' # this is the folder from which the code will process the images, make sure it aligns with the path specified in SpinView

self.host = "192.168.200.3" # ip of deformable mirror computer
self.user = "Utilisateur" # windows user of deformable mirror computer
self.password = "alls" # windows user password of deformable mirror computer
```
### Image processing 
##### X-ray count
Since we're imaging a phosphor screen, the X-ray count is measured by the brightness of the resulting image. The following function calculates the mean brightness per pixel of a single image. 

```python 
    def calc_xray_count(self, image_path):
        original_image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH) # IMREAD_ANYDEPTH, IMREAD_UNCHANGED ensure reading in 16bit
        median_filtered_image = cv2.medianBlur(original_image, 5) # adjustable median filter, currently set to 5 pixels (works well for data you sent)
        img_mean_count = median_filtered_image.mean() # mean count per single image
        return img_mean_count
```

### Communication
Sending data in real time for optimization using an FTP connection.
##### Sending new value
After processing of the data through the algorithm, we send a command text file to the mirror computer. 

```python
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
```
### Optimization algorithm
The image processing algorithm optimizes the X-ray flux by following the direction of count increase by adjusting the focus of the deformable mirror.

```python
    def process_images(self, new_images):
        self.initialize_image_files()
        new_images = [image_path for image_path in new_images if os.path.exists(image_path)]
        new_images.sort(key=os.path.getctime)
        for image_path in new_images:
            img_mean_count = self.calc_xray_count(image_path)
            self.n_images_count_sum += img_mean_count
            self.run_count += 1
            if self.run_count % self.n_images == 0:
                self.mean_count_per_n_images = np.mean(img_mean_count)
                self.count_history.append(self.mean_count_per_n_images)
                self.n_images_run_count += 1
                if self.n_images_run_count == 1:
                    print('-------------')                    
                    self.focus_history.append(self.initial_focus)  # update new focus
                    self.record_count_history.append(self.count_history[-1])  # this is the initial peak count
                    print(f"{image_path} {self.count_history[-1]}, initial focus {self.focus_history[-1]}")
                    self.new_focus = self.initial_focus + self.step * self.direction  # try the random direction
                    self.focus_history.append(self.new_focus)  # update new focus
                    print(f"first image, my initial direction is {self.direction}")
                    print('-------------')
                    continue # break out of the loop to print the initial focus and initial count (and not new focus for initial count)
                else:  # now we have enough data start optimization
                    count_gradient = (self.count_history[-1] - self.record_count_history[-1])/(self.record_count_history[-1]) # compare to record count
                    self.grad_history.append(count_gradient)
                    if self.count_history[-1] > self.record_count_history[-1]:
                        self.record_count_history.append(self.count_history[-1])  # this is the new current peak count
                        # continue this direction
                        self.new_focus = self.new_focus + self.step * self.direction
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print(f"new record count")
                    elif self.grad_history and self.min_grad_history and (np.abs(self.grad_history[-1]) < np.abs(self.min_grad_history[-1])):
                        self.min_grad_history.append(self.grad_history[-1])  # this is the new closest to the peak count
                        self.new_focus = self.new_focus + self.step * self.direction
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)  # update new focus
                        values[0] = self.focus_history[-1]
                        print(f"let's continue this direction")
                    elif np.abs((self.count_history[-1] - self.record_count_history[-1])/(self.record_count_history[-1])) <= self.tolerance:
                        self.n_images_count_sum = 0
                        self.mean_count_per_n_images  = 0
                        img_mean_count = 0
                        print("I'm close to the peak count, not changing focus")
                        continue  # we're close enough to the optimized value, let's stop trying to change focus
                    else:  # we're not closer than before, let's move to the other direction instead
                        self.new_focus = self.new_focus + self.step * self.direction * -1
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]
                        print("this is no good, switching direction")
        with open(MIRROR_FILE_PATH, 'w') as file:
            file.write(' '.join(map(str, values)))
            # self.upload_files_to_ftp() # send new txt file to deformable mirror computer
            print(f"mean_count_per_{self.n_images}_images {self.count_history[-1]}, current focus {self.focus_history[-1]}")  
            print('-------------') 
            # reset variables and process task
            self.n_images_count_sum = 0
            self.mean_count_per_n_images  = 0
            img_mean_count = 0
            QtCore.QCoreApplication.processEvents() 
```

**Please find the full code [here](https://drive.google.com/drive/folders/1mUsrw0kjHX-gVb9So5OYMLWE2qezmRzx?usp=sharing)**
