# Magtag
This is a previous version of the project created for an Adafruit Magtag e-ink display written in Circuit Python. This is not maintained and is here only for reference.

## Features
Connects to a MQTT server hosted on a Victron Cerbo over WiFi.  The Cerbo also uses a Node RED flow for the RV-C interface (Firefly G12) and automations.  Edit the settings.toml file to include your Cerbo SSID and password.

### Additional info
I eneded up moving this project to the AMOLED dsiplay using ESPHome as found in the root of this repo.  The Magtag project would have ocassional mqtt connectivity issues that needed additonal sorting out.  Refreshing the e-ink display was also a bit clunky.  Four buttons was a bit limiting for navigations and function.  If it were just a simple and fairly static display, it would have probably worked better.

![magtag](https://github.com/Erik98146/LaunchControl/blob/main/magtag/magtag.jpg)



