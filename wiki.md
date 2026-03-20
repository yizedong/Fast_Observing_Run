# FAST Observing Run — Operations Wiki

This wiki covers telescope limits, calibration procedures, startup/shutdown, the Galil TCS, and observer duties for the 60" telescope at FLWO.

---

## Table of Contents

1. [Telescope Limits](#telescope-limits)
2. [FAST Afternoon and Morning Calibrations](#fast-afternoon-and-morning-calibrations)
3. [60" Startup and Shutdown](#60-startup-and-shutdown)
4. [The Galil TCS](#the-galil-tcs)
5. [Restarting FAST and/or Galil](#restarting-fast-andor-galil)
6. [FAST IRAF Parameters (epar qfast)](#fast-iraf-parameters-epar-qfast)
7. [60" Observer Collateral Duties (48" Oversight)](#60-observer-collateral-duties-48-oversight)

---

## Telescope Limits

### Closure Criteria

> **Tip:** Current weather conditions are displayed on [the monitor to your right](https://raw.githubusercontent.com/yizedong/Fast_Observing_Run/main/figures/Monitor2.JPG). If that window is missing, open a browser and go to `127.0.0.1:8050`.

| Condition | Threshold |
|-----------|-----------|
| Wind (sustained) | ≥ 22 mph |
| Wind (gusts) | > 30 mph |
| Humidity | ≥ 85% |

### Opening Criteria

- Sustained improvement for **at least 20 minutes** as shown on the Ridge Weather website.
- **Good rule of thumb:** If Tierras is closed, the 60" should be closed as well.

**Weather data:** https://veritas.sao.arizona.edu/~whanlon/ridgeWeather.html

---

## FAST Afternoon and Morning Calibrations

> **Start calibrations at least 3 hours prior to 12-degree twilight** to ensure sufficient time, handle anomalies, and fill the camera with LN2.

**Dome must be closed and chamber lights off for all calibrations.**

### Calibration Sequence

| Type | Command | Notes |
|------|---------|-------|
| DARKS | `repeat 10 dark 900` | 10 × 15 min darks |
| BIAS | `bias 20` | 20 bias images |
| FLATS | `repeat 20 flat 10` | In yellow NTCS GUI: set Sky/Comp → **Comp**, Incand → **ON** |

### Afternoon vs. Morning

- **DARKS:** Only need to be done once. Preferred in the afternoon — morning darks risk being ruined by personnel turning on lights.
- **BIAS & FLATS:** Must be repeated in the morning after observing.

### LN2 Reminder

> **DO NOT FORGET TO FILL CAMERA WITH LN2 AT THE END OF THE NIGHT.**
> The camera has ~12 hours hold time and must be filled both in the afternoon and in the morning.

---

## 60" Startup and Shutdown

### Startup

1. Turn on drives on rack in Chart Room.
2. Verify Axis Motor Torque values are roughly **"0"** on the TCSGalil app (control room monitor). If an axis shows full deflection, "bump" the corresponding axis button on the hand paddle to zero it out.
   - **MAKE CERTAIN TORQUE VALUES ARE ZERO BEFORE SLEWING TO AN OBJECT!**
3. In the yellow TCS GUI, under **"Tele Tasks"** drop-down: turn on **"Dome On"** and **"Tracking On"**. (If at zenith, dome will rotate east to track.)
4. Verify the sun is not a danger; open the slit via: `192.33.141.174`
5. Turn off chamber A/C via: `192.33.141.117`
6. Open mirror covers via the wall-mounted switch in the chamber.

### Shutdown

1. Using the **Controls GUI** on the Galil computer, click **"Stow Mount at Zenith"**.
2. Verify the mount has stopped moving; turn off drives on rack in Chart Room.
3. Close mirror covers via the switch in the chamber.
4. Close slit via `192.33.141.174`; turn on chamber A/C via `192.33.141.117`.

> ### ⚠️ ALWAYS VERIFY TELESCOPES ARE STOWED AND DOME SLITS SHUT BEFORE DEPARTING AT THE END OF THE NIGHT

---

## The Galil TCS

### Introduction

In 2019, the old "Harvey" telescope control system was replaced by the **"Galil"** control system manufactured by DFM. The yellow NTCS GUI on the FLWO60 desktop is unchanged, but some functionality was lost and compatibility issues remain.

The Galil uses optical position sensors in RA and DEC with improved drive motors, making pointing much more reliable and making it extremely rare to lose pointing.

The Galil uses **three position sensing systems**, each with its own limits:
1. Mercury switch on the top southwest corner of the mirror cell
2. Mechanical "ramp" limits on each axis
3. Internal Galil limits

The chart room rack houses the Galil computer (bottom) and telescope drive controls (top).

### Start-up

The Galil App is usually running on the wall-mounted monitor in the control room. If not:
1. Confirm the guide computer is running in the appropriate configuration (guider up for FAST, no guider for Tress).
2. Confirm the Realtime System is **NOT** running on FLWO60.
3. Double-click **"Start TCS Galil"** on the wall-mounted monitor.
4. Once the Galil App is running, start the Realtime System.
5. Go to the rack and turn the **"Drives"** switch on (all other switches remain on).

### Shut-down

At end of night, turn the **"Drives"** switch on the rack to off. (Normally the only required step.)

### Useful GUIs (via Galil App → Operation menu)

| GUI | Purpose |
|-----|---------|
| Controls GUI | Stowing the telescope at end of night |
| Handpaddle GUI | Focus moves, especially with the automatic focus routine when Tres is mounted |

### Galil Peculiarities

- Drop-down menus on the yellow NTCS GUI still work.
- **Do NOT use "Stow Tele" or "Stow All" in the yellow GUI** — these will often crash the yellow GUI after stowing.
- **Correct procedure:** Stow via Controls GUI → **"Stow Mount at Zenith"**, then use the yellow GUI on FLWO60 to stow the dome.

### Known Galil Issues: Axis Failure

The Galil occasionally goes dead in one or both telescope axes (most commonly at start of night). Symptom: you load coordinates, click "Slew Enable", and an axis doesn't move.

**Recovery steps:**
1. Click **"Stow Mount at Zenith"** in the Controls GUI on the Galil monitor.
2. Exit the Realtime System on FLWO60.
3. Exit the Galil App (click "X" in upper right of GUI).
4. Restart the Galil App.
5. Restart the Realtime System.
6. Repeat if necessary.

### Recovering From a Limit Violation

First, try using the **hand paddle** to manually back the telescope off the violated limit.

If that fails, use the three **jumper plugs** (in a ziplock bag on the rack) for connectors labeled **"C2"**, **"DIR LIMITS"**, and **"INTERLOCK LIMITS"** on the back of the rack. Insert all three at once (it's hard to know which system flagged the limit). Then move the telescope off the limit via the hand paddle.

---

## Restarting FAST and/or Galil

### Axis Torque Pegged at Startup

If one or both axis torque indicators (RA/DEC) are pegged at a limit after turning on drives:
- Momentarily press the axis button opposite the torque direction on the hand paddle.
- If that fails, follow the full restart procedure below.

### Full Restart Procedure

1. Exit the Realtime System on FLWO60: type `bye` or `exit` in the black "Telshell" window. (If no command line, open a new xterm and type `killcom`.)
2. Once all Realtime System windows are gone (IRAF windows will remain), exit the TCS App on GALIL: click the "X" in the upper right of the main GUI, then click "yes" in the pop-up.
3. Double-click the yellow **"TCS Galil"** app on the desktop to restart it.
4. Confirm the previous `tcsserver` has been stopped on FLWO60:
   ```
   ps aux | grep tcsserver
   ```
   If still running:
   ```
   kill -9 *process number*
   ```
5. Restart FAST (the Realtime System) by typing in any xterm window on FLWO60:
   ```
   gofast &
   ```

> **Note:** If unable to kill the previous tcsserver, it will time out in 5–10 minutes.

---

## FAST IRAF Parameters (epar qfast)

Run `epar qfast` in IRAF (package: `procdata`, task: `qfast`) to set these parameters.

| Parameter | Default Value | Description |
|-----------|--------------|-------------|
| `Nobs` | 90 | FAST image number to process |
| `roodir` | `/rdata/fast/` | Spectrum image root directory |
| `obsdate` | `yyyy.mmdd` | Date of observation directory |
| `fcal` | `comp300+600` | Calibration file name |
| `caldir` | `qfast` | Calibration image directory |
| `row1` | 5 | First row for spectrum search |
| `row2` | 155 | Last row for spectrum search |
| `keepnam` | yes | Keep object name in file name |
| `apdisp` | yes | Display aperture and background |
| `imdisp` | no | Display raw image |
| `spdisp` | yes | Display spectrum |
| `quickre` | no | Cross-correlate redshift |
| `quickem` | no | Emission line redshift |
| `delquic` | no | Delete quick-look 1-D spectrum |
| `verbose` | no | Log progress |
| `mode` | h | — |

---

## 60" Observer Collateral Duties (48" Oversight)

### Overview

The 48" telescope operates autonomously via a robot/script. Under normal circumstances its operation is invisible to the 60" observer, but it requires monitoring.

### Monitoring 48" Images

**VNC into the 48" desktop:**
```
vncviewer flwo48:2 &
```
(Password is on the 60" monitor.)

**Open DS9 on the 48" desktop:**
```
ds9 &
```
(A DS9 window may already be open on the third desktop of flwo48.)

**Pull up latest 48" images in DS9:**
File → Open Other → Open Mosaic IRAF → navigate to `/rdata/kep/YYYY.MMDD`

### Controlling 48" Open/Close Status in Sketchy Weather

The 48" weather sensor can struggle with certain uniform cloud conditions. To override:

1. VNC into the 48" and go to the **2nd desktop**.
2. Find the GUI labeled **"FLWO 1.2m Weather"**.
3. Adjust the **"sky temperature"** entry field. Normal range: **-29 to -36**.
   - Lower the value to force the dome to close.
   - Raise the value to force the telescope to open.
4. Humidity and Wind criteria should be left as-is.
5. Clicking **"Weather Timeout"** or **"Sky Timeout"** bypasses the countdown and opens the dome immediately.

### 48" Error Recovery

Most errors can be corrected by exiting the robot and using the hand paddle.

**To stop the 48" robot:**
1. In the 48" Telshell, type `Ctrl-C` (or type `STOProbot` in an xterm).
2. In an xterm, type `Rstop` — this exits the robot and allows manual control.
3. After correcting the error, type `clear_robot` to stop error notifications at the 60" control room.
