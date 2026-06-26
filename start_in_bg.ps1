$logFile = "C:\radar-solar-copia\radar-solar-dev\server_output.log"
Set-Location "C:\radar-solar-copia\radar-solar-dev"
python -m src.main *> $logFile
