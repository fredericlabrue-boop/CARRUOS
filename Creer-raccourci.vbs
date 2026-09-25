' Cree le raccourci CARRUOS ALICE sur le Bureau.
'
' Un double-clic dessus lance CARRUOS sans console (Carruos.vbs), avec
' le logo du programme (carruos.ico). Le script peut etre relance autant
' de fois qu'on veut : il remplace le raccourci au lieu d'en empiler.
Option Explicit
Dim sh, fso, dossier, cible, bureau, lien, icone, ancien, vieux

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dossier = fso.GetParentFolderName(WScript.ScriptFullName)
cible   = fso.BuildPath(dossier, "Carruos.vbs")
bureau  = sh.SpecialFolders("Desktop")

If Not fso.FileExists(cible) Then
  WScript.Echo "  Carruos.vbs introuvable a cote de ce script."
  WScript.Quit 1
End If

' L'ancien raccourci, "CARRUOS.lnk", est retire -- mais seulement s'il
' pointe vers CE programme : un raccourci du meme nom qui menerait
' ailleurs n'est pas le notre, on n'y touche pas.
ancien = fso.BuildPath(bureau, "CARRUOS.lnk")
If fso.FileExists(ancien) Then
  Set vieux = sh.CreateShortcut(ancien)
  If LCase(vieux.TargetPath) = LCase(cible) Then fso.DeleteFile ancien
End If

Set lien = sh.CreateShortcut(fso.BuildPath(bureau, "Carruos Alice.lnk"))
lien.TargetPath       = cible
lien.WorkingDirectory = dossier
lien.Description      = "CARRUOS ALICE - scanner actions"
lien.WindowStyle      = 1

' L'icone n'est posee que si le fichier existe : un raccourci qui pointe
' vers une icone absente s'affiche en blanc sous Windows.
icone = fso.BuildPath(dossier, "carruos.ico")
If fso.FileExists(icone) Then lien.IconLocation = icone & ",0"
lien.Save

WScript.Echo "  Raccourci ""Carruos Alice"" cree sur le Bureau."
WScript.Echo "  Si l'ancien logo s'affiche encore : clic droit sur le Bureau,"
WScript.Echo "  Actualiser -- Windows garde les icones en memoire."
