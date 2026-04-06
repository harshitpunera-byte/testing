@echo off
SET "NODE_PATH=d:\Vocso\node_portable\node-v22.22.2-win-x64"
SET "PATH=%NODE_PATH%;%PATH%"
cd /d "d:\Vocso\testing\tender-ui"
echo Starting Frontend with Portable Node.js...
npm run dev
pause
