' Cree le raccourci CARRUOS ALICE sur le Bureau.
'
' Un double-clic dessus lance CARRUOS sans console, avec le logo du
' programme. Ce script se lance tout seul au premier demarrage de
' CARRUOS ; on peut aussi le double-cliquer, ou passer par la roue des
' reglages, ou par Carruos.bat (choix 3). Relance, il remplace le
' raccourci au lieu d'en empiler un second.
Option Explicit
Dim sh, fso, dossier, cible, bureau, lien, icone, copie, rep, ancien, vieux, wsc

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dossier = fso.GetParentFolderName(WScript.ScriptFullName)
cible   = fso.BuildPath(dossier, "Carruos.vbs")
bureau  = sh.SpecialFolders("Desktop")

If Not fso.FileExists(cible) Then
  WScript.Echo "Carruos.vbs introuvable a cote de ce script."
  WScript.Quit 1
End If

' Le raccourci passe par wscript.exe, nommement : sur un PC ou les
' fichiers .vbs s'ouvrent dans le Bloc-notes (reglage de securite
' courant), un raccourci pointant sur Carruos.vbs ouvrirait le script au
' lieu de lancer CARRUOS.
wsc = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\wscript.exe"

' L'ancien raccourci, "CARRUOS.lnk", est retire -- mais seulement s'il
' mene a CE programme : un raccourci du meme nom qui irait ailleurs n'est
' pas le notre, on n'y touche pas.
ancien = fso.BuildPath(bureau, "CARRUOS.lnk")
If fso.FileExists(ancien) Then
  Set vieux = sh.CreateShortcut(ancien)
  If LCase(vieux.TargetPath) = LCase(cible) Or _
     InStr(LCase(vieux.Arguments), LCase(cible)) > 0 Then fso.DeleteFile ancien
End If

Set lien = sh.CreateShortcut(fso.BuildPath(bureau, "Carruos Alice.lnk"))
lien.TargetPath       = wsc
lien.Arguments        =  & cible & 
lien.WorkingDirectory = dossier
lien.Description      = "CARRUOS ALICE - scanner actions"
lien.WindowStyle      = 1

' Windows garde les icones en memoire sous le NOM de leur fichier : un
' logo change sous le meme nom resterait l'ancien sur le Bureau. On en
' pose donc une copie dont le nom porte sa taille, dans le profil : un
' nouveau logo, c'est un nouveau nom, et Windows le relit.
icone = fso.BuildPath(dossier, "carruos.ico")
If fso.FileExists(icone) Then
  rep = sh.ExpandEnvironmentStrings("%APPDATA%") & "\Carruos"
  If Not fso.FolderExists(rep) Then fso.CreateFolder rep
  copie = rep & "\carruos-" & fso.GetFile(icone).Size & ".ico"
  If Not fso.FileExists(copie) Then fso.CopyFile icone, copie
  lien.IconLocation = copie & ",0"
End If
lien.Save

WScript.Echo "Raccourci ""Carruos Alice"" cree sur le Bureau." & vbCrLf & _
  "Si l'ancien dessin s'affiche encore : clic droit sur le Bureau, Actualiser."
