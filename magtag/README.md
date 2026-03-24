# Magtag
This is a previous version of the project created for an Adafruit Magtag e-ink display written in Circuit Python. This is no longer being developed is here only for reference.

## Features
Connects to a MQTT server hosted on a Victron Cerbo over WiFi.  The Cerbo also uses a Node RED flow for the RV-C interface (Firefly G12) and automations.  

## Deployment
1. Update Victron Cerbo with Large OS.  Enable MQTT server and Node RED.
2. Load ```launchControl-flow.json``` flow onto Node RED server hosted on the Cebo
3. Edit the ```settings.toml``` file to include your Cerbo SSID and password.
4. Copy the complete contents of this folder directly to the magtag.

### Additional info
I eneded up moving this project to the AMOLED dsiplay using ESPHome as found in the root of this repo.  Refreshing the e-ink display was a bit clunky, especially when navigating menus.  Four buttons was a bit limiting for navigation and functions.  If it were just a simple and fairly static display, it would have probably worked better.

![magtag](https://github.com/Erik98146/LaunchControl/blob/main/magtag/magtag.jpg)



