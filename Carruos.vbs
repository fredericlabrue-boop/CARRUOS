' Lance Carruos sans fenetre de console.
'
' pythonw.exe (ou pyw.exe) est la variante de Python sans console. La
' fenetre de l'application est celle de pywebview ; la console noire
' derriere elle n'apporte rien et masque le bureau.
Option Explicit
Dim sh, fso, dossier, py, cmd
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dossier = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dossier

If Not fso.FileExists(fso.BuildPath(dossier, "equity_scanner\app.py")) Then
  MsgBox "equity_scanner\app.py introuvable." & vbCrLf & vbCrLf & _
         "Carruos.vbs doit se trouver a cote du dossier equity_scanner.", _
         vbExclamation, "CARRUOS"
  WScript.Quit 1
End If

' pyw = lanceur Windows sans console, installe avec Python depuis
' python.org. On retombe sur pythonw si le lanceur n'est pas la.
py = "pyw"
On Error Resume Next
sh.Run "pyw -V", 0, True
If Err.Number <> 0 Then
  Err.Clear
  py = "pythonw"
  sh.Run "pythonw -V", 0, True
  If Err.Number <> 0 Then
    Err.Clear
    MsgBox "Python introuvable." & vbCrLf & vbCrLf & _
           "Installe-le depuis python.org en cochant" & vbCrLf & _
           """Add python.exe to PATH""," & vbCrLf & _
           "puis relance Carruos.bat et choisis 2 (Installer).", _
           vbExclamation, "CARRUOS"
    WScript.Quit 1
  End If
End If
On Error GoTo 0

cmd = py & " -m equity_scanner.app"
sh.Run cmd, 0, False
