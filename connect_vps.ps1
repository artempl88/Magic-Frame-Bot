$password = "IW7SYZs4fIsM"
$username = "root"
$server = "92.53.100.89"

# Создаем процесс SSH
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "ssh"
$psi.Arguments = "-o PasswordAuthentication=yes -o PreferredAuthentications=password $username@$server"
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
$process.Start()

# Ждем запроса пароля и отправляем его
Start-Sleep -Seconds 2
$process.StandardInput.WriteLine($password)
$process.StandardInput.Flush()

# Отправляем команды после подключения
Start-Sleep -Seconds 2
$process.StandardInput.WriteLine("whoami")
$process.StandardInput.WriteLine("uname -a")
$process.StandardInput.WriteLine("exit")

$output = $process.StandardOutput.ReadToEnd()
$errorOutput = $process.StandardError.ReadToEnd()

Write-Host "Output: $output"
Write-Host "Error: $errorOutput"

$process.WaitForExit()
