# Home Assistant IntesisHome integration (with config flow)
Development fork of the IntesisHome integration for Home Assistant

*This project is seeking a new maintainer, I haven't owned an Intesis device for many years, and no longer have the time to contribute to this project. Please get in touch if you are interested in taking this over. I've spent many mornings at the local coffee shop working on this project, if it has been useful to you please consider buying me a coffee with the link below, thank you!*

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/jnimmo)


This custom integration is a fork of the core integration for IntesisHome which adds experimental support for local control over HTTP for selected devices, local control over WMP (IntesisBox), and cloud control for IntesisHome, anywAir, airconwithme.
This is ready to integrate back into Home Assistant Core however it needs unit tests written for Config Flow for that to be able to happen, which I haven't got the time to invest in at this stage.

## Configuration
1. Install the integration
2. Navigate to integrations and add the IntesisHome integration through the user interface
3. Select the device type
4. Provide any additional required details (username, password, IP address) for your device


## Local control over HTTP (intesishome_local)
This experimental feature allows local control over HTTP for some device types.

## Local control over WMP (Intesisbox)
There are two forks for Intesisbox support. Intesisbox support was added to the pyintesishome library which this integration uses, however the original https://github.com/jnimmo/hass-intesisbox integration is likely to be better maintaned for the time being. 

## Device compatibility
| Device                  | Local HTTP - intesishome_local  |
| ----------------------- |:-------------| 
| DK-RC-WIFI-1B           | :white_check_mark: | 
| FJ-AC-WIFI-1B           | :white_check_mark: |
| MH-AC-WIFI-1            | :white_check_mark: |
| IS-ASX-WIFI-1           | :x:                |
