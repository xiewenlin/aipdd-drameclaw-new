Unicode True
!include "MUI2.nsh"

!define PRODUCT_NAME "古龙短剧"
!define PRODUCT_VERSION "2.0.1"
!define PRODUCT_PUBLISHER "古龙 Gulong Agent Engine"
!define APP_EXE "Gulong-ShortDrama-Native-2.0.1-x64.exe"

Name "${PRODUCT_NAME}"
OutFile "release\Gulong-ShortDrama-Native-Setup-2.0.1-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\GulongShortDrama"
InstallDirRegKey HKCU "Software\GulongShortDrama" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "assets\icon.ico"
UninstallIcon "assets\icon.ico"

!define MUI_ABORTWARNING
!define MUI_ICON "assets\icon.ico"
!define MUI_UNICON "assets\icon.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "安装古龙短剧" SecMain
  SetOutPath "$INSTDIR"
  Delete "$INSTDIR\Gulong-ShortDrama-Native-2.0.0-x64.exe"
  File "/oname=${APP_EXE}" "release\${APP_EXE}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\GulongShortDrama" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GulongShortDrama" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GulongShortDrama" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GulongShortDrama" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GulongShortDrama" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  CreateDirectory "$SMPROGRAMS\古龙短剧"
  CreateShortcut "$SMPROGRAMS\古龙短剧\古龙短剧.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$DESKTOP\古龙短剧.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\古龙短剧.lnk"
  Delete "$SMPROGRAMS\古龙短剧\古龙短剧.lnk"
  RMDir "$SMPROGRAMS\古龙短剧"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\GulongShortDrama"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GulongShortDrama"
SectionEnd
