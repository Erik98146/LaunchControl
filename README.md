# LaunchControl
A small and simple AMOLED control panel plus a web control panel for Jayco Terrain and Entegra Launch adventure vans with Lithionics/Victron components. Full RV-C integration.

## Features
- RV-C integration for status and control of all devices over the RV-C CAN bus network, duplicating Firefly controls
- Web control panel for Firefly controls and additonal automations
- Remote cloud control through VRM
- Georgeous mini AMOLED remote control panel for bed area
- Additional controls on Victron screen
- Timers for inverter, starlink and water pump
- Sleep timer to turn off devices at a set time each night
- Sets the clock on the Firefly display so it's always correct

The purpose of this project is to create a small remote control for the bed area that would allow at-a-glance status views and remote control of systems. I also wanted additional features such as a sleep timer to turn off devices automatically at night, and the option to power up some systems on a short timer (ie. turn on inverter for 1hr).

The selected microcontroller with capacitive touch AMOLED display is ideal for this purpose and the display can automatically be set to a very low level that wont disturb sleep.

## Technology Components
- Victron Cerbo: The Cerbo acts as the technology hub and gateway for the project and is enabled with a MQTT sever and Node RED.  Nodered is used as the RV-C to MQTT interface, provides the timer automations, provides the web panel, and provides the additional on-screen controls. The MQTT server acts as the gateway to to AMOLED panel.  Both Node RED and the MQTT server are supported by Victron and will survive system updates.
- Waveshare esp32-s3 micro controller with 1.75" round AMOLED touch display: This fast and responsive controller has a beautiful and very bright AMOLED display. The firmware is written with ESPHome and then compiled with espressif, so it's fast and reliable. It connects to the Cerbo over wifi using the cerbo built-in access point.  This allows the system to function without any other hardware, yet still allows the cerbo to make a secondary wifi connection for internet if desired. It can be ordered with a case and may be powered with USB-C or through a 5v connection in the back for hardwiring. The display has a night-time screen saver mode that provides a clock and at-a-glance status that emits very little light so that it isn't an annoyance when trying to sleep.  The display can also turn off at night.
