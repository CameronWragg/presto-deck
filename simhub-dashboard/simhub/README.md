# SimHub setup

SimHub's **Custom Serial Devices** plugin only writes to a COM port, so getting
telemetry onto the Presto over WiFi means giving SimHub a *virtual* COM port and
forwarding what comes out of it. Pick one of the three routes below - the
message you paste into SimHub is the same for all of them.

## 1. The message

Settings → Plugins → enable **Custom Serial devices**, then in the left menu:

1. **Add a new device**, pick your serial port (see the routes below), baud
   **115200**, and leave RTS/DTR alone.
2. Under **Update messages**, add a message, set the frequency to **10Hz**
   (the free SimHub build caps out there), and paste this NCalc expression:

```
'$SH|SPD=' + format([DataCorePlugin.GameData.NewData.SpeedKmh],'0') + '|RPM=' + format([DataCorePlugin.GameData.NewData.Rpms],'0') + '|MAX=' + format([DataCorePlugin.GameData.NewData.CarSettings_MaxRPM],'0') + '|GEAR=' + [DataCorePlugin.GameData.NewData.Gear] + '\n'
```

That produces one line per update:

```
$SH|SPD=137|RPM=6543|MAX=7800|GEAR=4
```

The trailing `\n` matters - the plugin sends no terminator of its own and the
Presto splits the stream on newlines.

### Optional extras

The device ignores keys it doesn't know, so you can append more without
changing the firmware. Two it *does* understand:

```
+ '|SLI=' + format([DataCorePlugin.GameData.NewData.CarSettings_RPMShiftLight1],'0.000')
+ '|PIT=' + format([DataCorePlugin.GameData.NewData.IsInPitLane],'0')
```

`SLI` is the car's real shift light point (a 0-1 fraction of max RPM, or an
absolute RPM - both are accepted). Check the exact names in SimHub's property
picker before adding them: an unresolved property makes the whole message fail.

## 2. Route A - com0com + the bridge script (free, all software)

```
SimHub ──► COM11 ║ COM12 ──► pc/simhub_bridge.py ──► WiFi ──► Presto
             (virtual null-modem pair)
```

1. Install [com0com](https://sourceforge.net/projects/com0com/) (use the signed
   release) and create a pair, e.g. `COM11` ↔ `COM12`.
2. Point SimHub's custom serial device at **COM11**.
3. On the PC: `pip install pyserial`, then

   ```
   python pc/simhub_bridge.py --serial COM12 --host <presto-ip> --echo
   ```

   `--echo` prints each forwarded line, which is the quickest way to confirm
   SimHub's message is well formed. Drop it once it works.

## 3. Route B - serial-over-TCP virtual COM (no script)

A virtual serial port driver that forwards to a TCP socket - HW VSP3, Perle
TruePort or similar - can talk to the Presto directly, since the device runs a
TCP server on port 5005.

1. Create a virtual COM port in client mode pointing at `<presto-ip>:5005`
   (raw/LITE mode, no telnet/RFC2217 protocol).
2. Point SimHub at that COM port.

Nothing else to run - but the driver is third-party and Route A is easier to
debug.

## 4. Route C - USB cable, no WiFi at all

The Presto shows up as a COM port itself, so SimHub can write straight to it.

1. Set `ENABLE_USB_SERIAL = True` in `device/config.py`.
2. Point SimHub's custom serial device at the Presto's COM port.

The catch: the firmware takes over the USB serial port, so Thonny/mpremote can
no longer interrupt the running program. Press the **reset** button to get the
board back for editing.

## Checking it works

- The status bar at the bottom of the Presto shows `DEMO` until real telemetry
  arrives, then `SIMHUB <fps>`.
- SimHub's **Log incoming data** option (in the serial port settings) shows what
  the device sends back - nothing, in this case; the link is one-way.
- No data? Run `python pc/fake_sim.py --host <presto-ip>` to prove the network
  path works independently of SimHub.
