# LaunchControl
A small and simple AMOLED control panel plus a web control panel for Jayco Terrain and Entegra Launch adventure vans with Lithionics/Victron components. Full RV-C integration.

## Features
- RV-C integration for status and control of all devices over the RV-C can-bus network
- Web control panel
- Remote cloud control through VRM
- Georgeous mini AMOLED remote control panel for bed area
- Additional controls on Victron screen
- Timers for inverter, starlink and water pump
- Sleep timer to turn off devices at a set time each night
- Climate controls

The purpose of this project was to create a small remote control for the bed area that would allow at-a-glance status views and remote control of systems. I also wanted additional features such as a sleep timer to turn off devices automatically at night, and the option to power up some systems on a short timer (ie. turn on inverter for 1hr).

The selected microcontroller with capacitive touch AMOLED display is ideal for this purpose and the display can automatically be set to a very low level that wont disturb sleep.

## Technology Components
- Victron Cerbo: The Cerbo acts as the technology hub and gateway for the project and will be enabled with MQTT sever and Nodered.  Nodered is used as the RV-C to MQTT interface, provides the timer automations, provides the web panel, and provides the additional on-screen controls. The MQTT server acts as the gateway to to AMOLED panel.  Both Nodered and the MQTT server are supported by Victron and will survive system updates.
- Waveshare 1.75" round AMOLED touch display and esp
