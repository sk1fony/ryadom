# Ryadom

[Русский](README.ru.md)

Transfer files and text between devices over a local network

[Download](https://github.com/sk1fony/ryadom/releases/tag/ryadom)

## Run

Install [Python 3.10+](https://www.python.org/downloads/), download the project and unpack it

| System | Launch |
| --- | --- |
| Windows | Open `start.bat` |
| macOS | Run `sh start.command` |
| Linux | Run `sh start.sh` |

Run commands from the project folder. **Keep the terminal open while using Ryadom**

## Connect

1. Connect your phone and computer to the same local network
2. Scan the QR code
3. Enter the code on your phone

If the phone cannot connect, check that your VPN allows local network access and the firewall allows Python on private networks

## Files and text

Files received on the PC are saved to `~/Downloads/Ryadom`. Default limit: **6 GiB per file**

Refreshing the QR disconnects paired devices. Transfers use local HTTP without encryption, so use a trusted network

## Options

```sh
python3 bootstrap.py --port 9000 --storage ./received --max-file-mb 6144
```

Use `python` on Windows. All options are available with `--help`

[MIT](LICENSE)
