Set-Variable -Name fpath -value "$env:USERPROFILE/satellite.jpg"
Set-Variable -Name BASEURL "https://localhost:7000"  # update this
Invoke-WebRequest "$BASEURL/rammb/goes-16.jpg?sector=conus&width=2560&height=1440&filters=trim,scale,timestamp" -OutFile $fpath
set-itemproperty -path "HKCU:\Control Panel\Desktop" -name WallPaper -value $fpath
Sleep -seconds 5
RUNDLL32.EXE USER32.DLL,UpdatePerUserSystemParameters ,1 ,True
