@echo off
rem Docker-backed OpenFOAM launcher for the Slipstream backend (Windows).
rem Forwards "openfoam -c <shell>" to backend/scripts/openfoam_docker.py,
rem which runs the stage inside the opencfd OpenFOAM Docker image.
python "%~dp0openfoam_docker.py" %*
exit /b %errorlevel%
