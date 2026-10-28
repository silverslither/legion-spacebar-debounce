# Legion Spacebar Debounce

Hacky evdev script to prevent extraneous spacebar KEYDOWN events emitted by Legion laptop keyboards.

(Causes of the bug are speculation, I haven't looked at the EC firmware) When a key is pressed in a certain way, it may cause the EC to send a KEYDOWN, then debounce all but a KEYUP event, giving the appearance that the key is released even when it is physically pressed. Then, when any other key event is emitted, the EC repolls the entire matrix, and a second KEYDOWN event will be emitted for that first keypress (if the key is still held). This can happen for any key, but is most prominent on the spacebar, and is easily reproducible on some laptop models by simply pressing the very edge of the key (which I do very often as I use a wide layout, which shifts my right hand to the right by an additional key width).

## Installation

Depends on Python 3.10+ (you may modify the script to run on earlier versions, I'm not supporting it), and the `evdev` package.

Install the Python script in `/usr/local/bin`, and install the given systemd unit. If any other key remapping daemon is active (such as keyd), add `legion-spacebar-debounce.service` to that daemon's `Requires` and `After` using an override.
