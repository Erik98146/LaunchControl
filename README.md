# LaunchControl 
A small and simple AMOLED control panel plus a web control panel for Jayco Terrain and Entegra Launch adventure vans with Lithionics/Victron components. Full RV-C integration.  The implementation of this is a bit involved, but once setup it's been hands-off and very reliable.  It launches behind the scenes whenever power is applied.

## Features
- RV-C integration for status and control of all devices over the RV-C network, duplicating (and improving) Firefly controls
- Web control panel for Firefly controls and additonal automations
- New automation controls added to Victron screen
- Remote cloud control through VRM
- Gorgeous mini AMOLED remote control panel for bed area remote control
- Timers for inverter, starlink and water pump
- Sleep timer to turn off devices at a set time each night
- Sets the clock on the Firefly display so it's always correct

The purpose of this project is to create a small remote control for the bed area that would allow at-a-glance status views and remote control of systems. I also wanted additional features such as a sleep timer to turn off devices automatically at night, and the option to power up some systems on a short timer (ie. turn on inverter for 1hr). Once setup, the system is very stable and reliable.

The selected microcontroller with capacitive touch AMOLED display is ideal for this purpose and the display can automatically be set to a very low level at night that wont disturb sleep.

I used Ruuvi tags which are small wireless thermometers to get the temperature inside and outside the van. They integrate directly with the Cerbo over Bluetooth.

The Node RED flow can be installed on the Cerbo without using the remote AMOLED display.  This will provide all other functionality and the web dashboard.

## Technology Components
- **Victron Cerbo:** The Cerbo acts as the technology hub and gateway for the project and is enabled with a MQTT sever and Node RED.  A Node RED flow is used as the RV-C to MQTT interface, provides the timer automations, provides the web panel, and provides the additional Cerbo on-screen controls. The MQTT server acts as the gateway to the AMOLED panel.  Both Node RED and the MQTT server are supported by Victron and will survive system updates.
- **Optional Waveshare esp32-s3 micro controller with 1.75" round AMOLED touch display:** This fast and responsive controller has a beautiful and very bright AMOLED display. The firmware is written with ESPHome and then compiled with espressif, so it's fast and reliable. It connects to the Cerbo over wifi using the cerbo built-in access point.  This allows the system to function without any other hardware, yet still allows the cerbo to make a secondary wifi connection for internet if desired. It can be ordered with a case and may be powered with USB-C or through a 5v connection in the back for hard-wiring. The display has a night-time screen saver mode that provides a clock and at-a-glance status that emits very little light so that it isn't an annoyance when trying to sleep.  The display can also turn off at night.
-- Order the version with protective case: https://www.waveshare.com/esp32-s3-touch-amoled-1.75.htm?sku=31262

![Web Dashboard](https://github.com/Erik98146/LaunchControl/blob/main/images/WebDashboard-sm.jpg?raw=true)    ![Victron Screen](https://github.com/Erik98146/LaunchControl/blob/main/images/VictronScreen-sm.jpg?raw=true)     ![AMOLED](https://github.com/Erik98146/LaunchControl/blob/main/images/AMOLED-sm.jpg)   

Video:https://youtu.be/Vuok86__elU

## Deployment
Navigate to the Releases button to the right for the latest files:
- ```LaunchcControl-flow.json``` This is the NodeRED flow to load onto the Cerbo
- ```launchcontrol.yaml``` This is the ESPHome file for the AMOLED display
- ```van.png``` logo file

### Cerbo
Enable Node RED and MQTT. Enable the access point. Install and deploy the Node RED flow.  Detailed instructions:
1. Connect the Cerbo to the internet
2. Update the Cerbo firmware, and choose the "large" image (this will allow for Node RED).  Choose to use the new GUI if you haven't already.
3. From ```Settings/Integrations``` *enable MQTT access*.
4. From ```Settings/Integrations``` *Enable Node RED*.
5. From ```Settings/Connectivity/WiFi``` enable *Create access point*. Make a password. The list of wifi networks now will include venus-xxxxxxxxxxxxx.  Do not select it, but make a note of it so you can connect your phone or PC (for when you don't have the Cerbo connected to a access point or internet) and for connecting the display later.
6. Setup your free VRM account for cloud access and remote control and link it to your Cerbo at: https://vrm.victronenergy.com
7. Connect to your system over VRM via the web browser link in the previous step
8. Choose Venus OS Large from the VRM web menu and launch Node-Red
9. Download ```LaunchcControl-flow.json``` file from releases
10. From the top right Node RED menu, select *import* and import the flow
11. Install the flowfuse dashboard (for the ui buttons):
  - Open the menu in the top-right of Node-RED.
  - Click "Manage Palette".
  - Switch to the "Install" tab
  - Search node-red-dashboard
  - Install the @flowfuse/node-red-dashboard package (not node-red/node-red-dashboard)
12. Press *Deploy*

Note: **Check the release notes, most updates do not require updating the Node RED flow.**  If you are updating the Node RED flow from a previous version of LaunchControl, be sure to delete the old flow from within Node RED **AFTER** adding the new flow by right clicking on the old flow at the top, selecting *Delete* and then clicking *Deploy*. 

### Waveshare AMOLED Touchscreen (optional)
Compile and flash the firmware.  Detailed instructions:
1. Install ESPHome on your computer using the **manual** method: https://esphome.io/guides/installing_esphome/
2. **Do NOT use the Python install manager**.  **Do NOT use the latest version**, it's not compatible (use 3.13.x): https://www.python.org/downloads/windows/
3. install Git on your computer: https://git-scm.com/install/windows
4. Download all files from releases (on the right side) and place them in a common folder
5. Connect the Waveshare AMOLED display to your computer with USB
6. Open a command prompt and navigate to the directory with the downloaded files
7. Send the compile command: ```esphome run launchcontrol.yaml``` (see note below regarding compile errors)
8. After it compiles, select the option to upload using the COM port USB serial device
9. Move to the van or within range of the Cerbo wifi. Connect the display to USB power.  1 minute after launch, it will start the setup portal hot spot. Use your phnone and connect to SSID ```LaunchControl-Config``` and select venus-xxxxxx from the list of WiFi networks available. Enter the password you setup previously on the Cerbo and save (this will connect the wifi of the display to the Cerbo and save the settings). The device should launch and become functional in a moment.

Future reboots happen in just a couple seconds, but it will take about 1 minute afetr a cold start of the van for the Victron Cerbo to power up and begin to send data.

Minor complilation warnings and errors are ok, but if there is a failure you can try to delete the build componenets and it will automatically download them again next time you compile. navigate to ```.esphome/build``` and delete the entire campervan32 folder and try the compile command again.

## Usage

### Web Control Panel
  The web control panel can be accessed locally or over the internet if your Cerbo has web access
  ### Internet Access (best option if online)
  1. Connect to VRM from your device: https://vrm.victronenergy.com
     - Navigate to Venus OS Large
         - Launch the Node-Red Dashboard  
       Note: if you are receiveing an error about an expired token, refresh the Venus OS Large page and try again.
  
     - Optionally open the *Console* for remote screen access  

  ### Local access (no internet or access point installed)
  1. Connect your device to the Cerbo wifi access point noted above
  2. Open a web browser to: https://172.24.24.1:1881/dashboard/page1

### Cerbo Controls
The new cerbo controls can be found in the top left corner of the Victron touchscreen.  Currently, the controls allow for launching device timers and the sleep timer.  The sleep timer defaults to turning off the inverter, water pump, and starlink at 2am, so this can be enabled without any extra hardware or effort.

### Waveshare AMOLED Touchscreen
If there are issues with this, check the settings screen to see if it has wifi and mqtt connectivity. If the Node RED dashboard is working and there is connectivity, the device should be working.

See this YouTube video for use:  https://youtu.be/Vuok86__elU

## Limitations

## Roadmap
- Using the built-in gyroscope to build a parking level assist function
- Create a driving version for mounting to the dashboard (battery, devices, alternator, climate, lights, parking level assist)
- Enable/disable starlink option
- Enable/Disable ruuvi tags



