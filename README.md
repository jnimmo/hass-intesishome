# Home Assistant IntesisHome integration (with config flow)
Development fork of the IntesisHome integration for Home Assistant

*This project is seeking a new maintainer, I haven't owned an Intesis device for many years, and no longer have the time to contribute to this project. Please get in touch if you are interested in taking this over. I've spent many mornings at the local coffee shop working on this project, if it has been useful to you please consider buying me a coffee with the link below, thank you!*

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/jnimmo)


This custom integration is a fork of the core integration for IntesisHome which adds experimental support for local control over HTTP for selected devices, local control over WMP (IntesisBox), and cloud control for IntesisHome, anywAir, airconwithme.
This is ready to integrate back into Home Assistant Core however it needs unit tests written for Config Flow for that to be able to happen, which I haven't got the time to invest in at this stage.

## Configuration
1. Add this custom repository to HACS, or manually download the files into your custom_components directory
2. Restart Home Assistant
3. [![Start IntesisHome configuration in Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=intesishome) or navigate to integrations and add the IntesisHome integration through the user interface 
5. Select the device type
6. Provide any additional required details (username, password, IP address) for your device

## Cloud control
Control of IntesisHome, anywAir, airconwithme devices generally is through a persistent connection to the Intesis cloud.
This requires outgoing HTTPS access to connect to the API, then control moves to a TCP port specified by the API. 

## Local control

### HTTP (intesishome_local)
This experimental feature allows local control over HTTP for devices which expose an HTTP web server on port 80 (http://ip/api.cgi)
| Device                  | HTTP - intesishome_local | 
| ----------------------- |:-------------------------| 
| DK-RC-WIFI-1B           | :white_check_mark:       | 
| FJ-AC-WIFI-1B           | :white_check_mark:       |
| MH-AC-WIFI-1            | :white_check_mark:       |
| IS-ASX-WIFI-1           | :x:                      |

### WMP (Intesisbox)
There are two forks for Intesisbox support. Intesisbox support was added to the pyintesishome library which this integration uses, however the original https://github.com/jnimmo/hass-intesisbox integration is likely to be better maintaned for the time being. 
