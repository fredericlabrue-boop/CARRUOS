' Cree un raccourci CARRUOS sur le Bureau.
Option Explicit
Dim sh, fso, dossier, cible, lien, icone
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dossier = fso.GetParentFolderName(WScript.ScriptFullName)
cible   = fso.BuildPath(dossier, "Carruos.vbs")

If Not fso.FileExists(cible) Then
  WScript.Echo "  Carruos.vbs introuvable a cote de ce script."
  WScript.Quit 1
End If

Set lien = sh.CreateShortcut(fso.BuildPath(sh.SpecialFolders("Desktop"), _
                                           "CARRUOS.lnk"))
lien.TargetPath       = cible
lien.WorkingDirectory = dossier
lien.Description      = "CARRUOS - scanner actions"

' L'icone n'est posee que si le fichier existe : un raccourci qui pointe
' vers une icone absente s'affiche en blanc sous Windows.
icone = fso.BuildPath(dossier, "carruos.ico")
If fso.FileExists(icone) Then lien.IconLocation = icone
lien.Save

WScript.Echo "  Raccourci CARRUOS cree sur le Bureau."
