param([Parameter(Mandatory=$true)][string]$OutputDirectory,[Parameter(Mandatory=$true)][string]$SpecSHA256,[Parameter(Mandatory=$true)][string]$OwnerDecision,[Parameter(Mandatory=$true)][string]$OwnerDecisionSHA256,[Parameter(Mandatory=$true)][string]$PythonExecutable)
$ErrorActionPreference='Stop'
$spec=Join-Path $OutputDirectory 'BATCH_SPEC.json'
if((Get-FileHash -LiteralPath $spec -Algorithm SHA256).Hash.ToLowerInvariant() -ne $SpecSHA256){throw 'Frozen specification mismatch; no credential entry or call'}
if((Get-FileHash -LiteralPath $OwnerDecision -Algorithm SHA256).Hash.ToLowerInvariant() -ne $OwnerDecisionSHA256){throw 'Owner decision mismatch; no credential entry or call'}
$decision=Get-Content -LiteralPath $OwnerDecision -Raw|ConvertFrom-Json
if($decision.approved -ne $true -or $decision.owner_identifier -ne 'programmerONE' -or $decision.spec_sha256 -ne $SpecSHA256 -or $decision.decision -ne 'APPROVE_ONE_PAIRED_MODEL_WORKFLOW_PILOT'){throw 'Exact owner admission missing'}
$enteredLocally=$false
try {
  if(-not $env:NEBIUS_API_KEY){
    Add-Type -AssemblyName System.Windows.Forms
    $dialog=New-Object System.Windows.Forms.Form
    $dialog.Text='SE6 paired pilot - private Nebius entry'
    $dialog.Width=530;$dialog.Height=220;$dialog.StartPosition='CenterScreen';$dialog.TopMost=$true
    $label=New-Object System.Windows.Forms.Label
    $label.Text='Enter your existing Nebius key. Masked, not saved. Only the exact approved pilot runs; no key-test call.'
    $label.Left=20;$label.Top=20;$label.Width=470;$label.Height=45
    $entry=New-Object System.Windows.Forms.TextBox
    $entry.UseSystemPasswordChar=$true;$entry.Left=20;$entry.Top=75;$entry.Width=470
    $button=New-Object System.Windows.Forms.Button
    $button.Text='Use locally';$button.Left=20;$button.Top=115;$button.Width=150;$button.DialogResult=[System.Windows.Forms.DialogResult]::OK
    $cancel=New-Object System.Windows.Forms.Button
    $cancel.Text='Cancel';$cancel.Left=190;$cancel.Top=115;$cancel.Width=120;$cancel.DialogResult=[System.Windows.Forms.DialogResult]::Cancel
    $dialog.Controls.AddRange(@($label,$entry,$button,$cancel));$dialog.AcceptButton=$button;$dialog.CancelButton=$cancel
    $choice=$dialog.ShowDialog()
    if($choice -ne [System.Windows.Forms.DialogResult]::OK -or -not $entry.Text){throw 'Credential MISSING; no provider call'}
    $env:NEBIUS_API_KEY=$entry.Text;$entry.Clear();$enteredLocally=$true;$dialog.Dispose()
  }
  $env:PYTHONDONTWRITEBYTECODE='1';$env:PYTHONNOUSERSITE='1'
  & $PythonExecutable -B (Join-Path $PSScriptRoot 'run_model_workflow_pilot.py') execute --output $OutputDirectory --owner-approval $OwnerDecision --owner-approval-sha256 $OwnerDecisionSHA256
  exit $LASTEXITCODE
} finally {
  if($enteredLocally){Remove-Item Env:\NEBIUS_API_KEY -ErrorAction SilentlyContinue}
}
