# Running the SQLAlchemy study on a Windows PC

The study runs inside WSL2 (Linux inside Windows). Setup once, then one command.

## 1. One-time setup

1. Open **PowerShell as Administrator** and run:
   ```
   wsl --install -d Ubuntu
   ```
   Restart when asked. Open **Ubuntu** from the Start menu and create a user name and password.
2. In the Ubuntu window:
   ```
   sudo apt update && sudo apt install -y git python3 python3-venv python3-dev build-essential gh
   python3 --version        # must be 3.12 or newer (Ubuntu 24.04 has 3.12)
   gh auth login            # GitHub, HTTPS, log in with a browser: lets the script push the results back
   ```
3. Get the code **inside Linux** (not under /mnt/c, which is many times slower):
   ```
   cd ~
   git clone https://github.com/thnam02/Proviso.git
   cd Proviso
   git checkout phase4-pilot
   ```

## 2. Run

```
cd ~/Proviso
git pull
bash research/sqla/run_all.sh
```

- It installs its own Python environment (pinned versions), fetches SQLAlchemy and NameRTS, and runs every stage
  on all cores but one.
- Expected time on 8 cores / 16 GB: roughly 6–8 hours (the real-commit stage is the longest: each commit gets its own
  coverage map, testmon database and NameRTS set-up). Leave the window open; the PC must not sleep
  (Windows Settings > Power > Sleep: Never, while it runs). More memory lets more NameRTS stages run in parallel.
- **Safe to stop and restart**: run the same command again and it continues where it stopped.
- Progress: `tail -f ~/proviso-work/sqla/run.log` in a second Ubuntu window.

## 3. Results

At the end the script commits `research/sqla/results/` and pushes it to GitHub. If pushing fails, it packs the
results into `~/proviso-sqla-results.tar.gz`; in Windows Explorer that file is at `\\wsl$\Ubuntu\home\<your user>\`
and can be attached in the chat.

## If something goes wrong

Send the last lines of `~/proviso-work/sqla/run.log` and of the newest `~/proviso-work/sqla/*.w*.log`.
