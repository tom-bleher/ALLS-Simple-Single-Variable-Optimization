
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
from pyqtgraph.Qt import QtCore, QtWidgets # needs to be installed 
import sys
```

##### Hard-coded paths
The code includes a number of hard coded paths, before proceeding adjust them accordingly to your setup.

```python
# computer near chamber
MIRROR_FILE_PATH = r'mirror_command/mirror_change.txt' # this is the txt file the code writes to
self.IMG_PATH = r'C:\Users\blehe\Desktop\Betatron\images' # this is the folder from which the code will process the images, make sure it aligns with the path specified in SpinView

self.ftp = FTP()
self.ftp.connect(host="192.168.200.3") # ip of deformable mirror computer
self.ftp.login(user="Utilisateur", passwd="alls") # windows user and password of deformable mirror computer
```
### Image processing 
##### X-ray count
Since we're imaging a phosphor screen, the X-ray count is measured by the brightness of the resulting image. The following function calculates the mean brightness per pixel of a single image. 

```python 
    def calc_count_per_image(self, image_path):
        # read the image in 16 bit
        original_image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
        # apply median blur on image
        median_blured_image = cv2.medianBlur(original_image, 5)
        # calculate mean brightness of blured image
        self.single_img_mean_count = median_blured_image.mean()
        # return the count (brightness of image)
        return self.single_img_mean_count
```

### Communication
Sending data in real time for optimization using an FTP connection.
##### Sending new value
After processing of the data through the algorithm, we send a command text file to the mirror computer. 

```python
    # method used to send the new values to the deformable mirror computer via FTP
    def upload_files_to_ftp(self):
        base_directory = 'Server'
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
```
### Optimization algorithm
The image processing algorithm optimizes the X-ray flux by following the direction of count increase by adjusting the focus of the deformable mirror.

```python
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
                        self.mean_count_per_image_group  = 0
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
                    else:  # we're not closer than before, let's move to the other direction instead
                        self.new_focus = self.new_focus + self.step_size * self.direction * -1
                        self.new_focus = int(np.round(np.clip(self.new_focus, self.lower_bound, self.upper_bound)))
                        self.focus_history.append(self.new_focus)
                        values[0] = self.focus_history[-1]

                        print("This is no good, switching direction")
                # after the algorithm adjusted the value and wrote it to the txt, send new txt to deformable mirror computer
                self.upload_files_to_ftp()
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
                self.mean_count_per_image_group  = 0
                self.single_img_mean_count = 0

                QtCore.QCoreApplication.processEvents()
```
