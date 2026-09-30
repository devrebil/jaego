Option Explicit

Dim shell, files, baseDir, pythonw, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")

baseDir = files.GetParentFolderName(WScript.ScriptFullName)
pythonw = baseDir & "\.venv\Scripts\pythonw.exe"

If Not files.FileExists(pythonw) Then
    pythonw = "pythonw.exe"
End If

command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & baseDir & "\launcher.py" & Chr(34)
shell.CurrentDirectory = baseDir
shell.Run command, 0, False
