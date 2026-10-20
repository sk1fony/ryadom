# Ryadom

[Русский](README.ru.md)

Send files and text between your computer and phone over a local network, without an account or a phone app

## Run

Install [Python 3.10+](https://www.python.org/downloads/), download the project and unpack it

| System | Launch |
| --- | --- |
| Windows | Open `start.bat` |
| macOS | Run `sh start.command` |
| Linux | Run `sh start.sh` |

Run commands from the project folder. The first launch needs internet to install the QR library. After that, Ryadom works offline. Keep the terminal open while using it

## Connect

1. Connect your phone and computer to the same local network
2. Scan the QR code shown on the computer
3. Enter the six-digit code on your phone

The code changes every 15 seconds. Use **Send / Receive** to exchange files or text. Switch the interface language with **En / Ru**

If the phone cannot connect, check that your VPN allows local network access and the firewall allows Python on private networks

## Files and text

Files received on the computer are saved to `~/Downloads/Ryadom`. The default limit is **6 GiB per file**

Files shared from the computer are temporary copies. Received files stay after closing Ryadom; text is cleared on shutdown or QR refresh

Refreshing the QR disconnects paired devices. Transfers use local HTTP without encryption, so use a trusted network

## Options

```sh
python3 bootstrap.py --port 9000 --storage ./received --max-file-mb 6144
```

Use `python` on Windows. Add `--help` for all options

[MIT](LICENSE)
