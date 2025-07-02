@echo off
echo Building Docker image...
docker build -t brfc-agent .

echo.
echo Stopping existing container (if any)...
docker stop brfc-agent-container >nul 2>&1
docker rm brfc-agent-container >nul 2>&1

echo.
echo Running new container...
docker run -p 8000:8000 -v "C:/Users/Johann/OneDrive/The Botes Family/Johann's Documents/Agents/BRFC Agents/winged-pen-413708-d067ac48546c.json":/app/creds.json brfc-agent

echo.
echo BRFC Reporting Agent restarted successfully.
pause
