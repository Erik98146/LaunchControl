# LaunchControl
A small and simple AMOLED control panel plus a web control panel for Jayco Terrain and Entegra Launch adventure vans with Lithionics/Victron components. Full RV-C integration.

## Features
- RV-C integration for status and control of all devices over the RV-C CAN bus network, duplicating (and improving) Firefly controls
- Web control panel for Firefly controls and additonal automations
- Remote cloud control through VRM
- Georgeous mini AMOLED remote control panel for bed area
- Additional controls on Victron screen
- Timers for inverter, starlink and water pump
- Sleep timer to turn off devices at a set time each night
- Sets the clock on the Firefly display so it's always correct

The purpose of this project is to create a small remote control for the bed area that would allow at-a-glance status views and remote control of systems. I also wanted additional features such as a sleep timer to turn off devices automatically at night, and the option to power up some systems on a short timer (ie. turn on inverter for 1hr). Once setup, the system is very stable and reliable.

The selected microcontroller with capacitive touch AMOLED display is ideal for this purpose and the display can automatically be set to a very low level that wont disturb sleep.

The Node RED flow can be installed on the Cerbo without using the remote AMOLED display.  This will provide all other functionality and the web dashboard.

## Technology Components
- Victron Cerbo: The Cerbo acts as the technology hub and gateway for the project and is enabled with a MQTT sever and Node RED.  A Node RED flow is used as the RV-C to MQTT interface, provides the timer automations, provides the web panel, and provides the additional Cerbo on-screen controls. The MQTT server acts as the gateway to to AMOLED panel.  Both Node RED and the MQTT server are supported by Victron and will survive system updates.
- Waveshare esp32-s3 micro controller with 1.75" round AMOLED touch display: This fast and responsive controller has a beautiful and very bright AMOLED display. The firmware is written with ESPHome and then compiled with espressif, so it's fast and reliable. It connects to the Cerbo over wifi using the cerbo built-in access point.  This allows the system to function without any other hardware, yet still allows the cerbo to make a secondary wifi connection for internet if desired. It can be ordered with a case and may be powered with USB-C or through a 5v connection in the back for hardwiring. The display has a night-time screen saver mode that provides a clock and at-a-glance status that emits very little light so that it isn't an annoyance when trying to sleep.  The display can also turn off at night.
-- Order the version with protective case: https://www.waveshare.com/esp32-s3-touch-amoled-1.75.htm?sku=31262

## Deployment
### Cerbo
1. Connect the Cerbo to the internet
2. Update the Cerbo firmware, and choose the "large" image (this will allow for Node RED).  Choose to use the new GUI if you haven't already.
3. From ```Settings/Integrations``` *enable MQTT access*.
4. From ```Settings/Integrations``` *Enable Node RED*.
5. From ```Settings/Connectivity/WiFi``` enable *Create access point*. Make a password. The list of wifi networks now will include venus-xxxxxxxxxxxxx.  Do not select it, but make a note of it so you can connect your phone or PC (for when you don't have the Cerbo connected to a access point or internet) and for connecting the display later.
6. Setup your free VRM account for cloud access and remote control at: https://vrm.victronenergy.com
7. Connect to your system over VRM
8. Choose Venus OS Large and launch Node-Red
9. Download the **LaunchControl-flow.json** file from this github project
10. From the top right menu, select *import* and import the flow
11. Press Deploy

### Waveshare AMOLED Touchscreen (optional)
1. Install ESPHome on your computer using the manual method: https://esphome.io/guides/installing_esphome/
2. Do NOT use the Python install manager.  Note the warning to NOT use the latest version (use 3.13.x): https://www.python.org/downloads/windows/
3. install Git on your computer: https://git-scm.com/install/windows
4. Download the **launchcontrol.yaml** file from this repo
6. Download the **secrets.yaml** file from this repo
7. Edit the secrets file and add the name of the cerbo access point and password noted earlier (or your router if thats your preference)
8. Find the IP address of your cerbo and enter that as the mqtt server
9. Save the secrets file
10. Connect the Waveshare AMOLED display with USB and use the device manager to find the com port
11. Open a command prompt and navigate to the directory with the launchcontrol.yaml and secrets.yaml file
12. Send the compule command: ```esphome run launchcontrol.yaml```
13. After it compiles, select the option to upload using the COM port USB serial device

Minor complilation warnings and errors are ok, but if there is a failure you can try to delete the build componenets and it will automatically download them again next time you compile. navigate to ```.esphome/build``` and delete the entire campervan32 folder

## Usage
### Web Control Panel
The web control panel can be accessed locally or over the internet if your Cerbo has web access
### Internet Access (best option if online)
1. Connect to VRM from your device: https://vrm.victronenergy.com
   - Navigate to Venus OS Large
       - Launch the Node-Red Dashboard
   - Optionally open the *Console* for remote screen access
Note: if you are receiveing an error about an expired token, refresh the Venus OS Large page and try again.
### Local access
1. Connect your device to the Cerbo wifi access point noted above
2. Open a web browser to: https://[CERBO IP ADDRESS]:1881/dashboard/page1
