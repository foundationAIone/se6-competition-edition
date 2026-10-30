param(
  [Parameter(Mandatory=$true)][string]$Specification,
  [Parameter(Mandatory=$true)][string]$SpecSHA256,
  [Parameter(Mandatory=$true)][string]$ClaimStore,
  [Parameter(Mandatory=$true)][string]$OwnerDecision,
  [Parameter(Mandatory=$true)][string]$OwnerDecisionSHA256,
  [Parameter(Mandatory=$true)][string]$PythonExecutable
)
$ErrorActionPreference='Stop'
$appRoot=Split-Path -Parent $PSScriptRoot
if((Get-FileHash -LiteralPath $Specification -Algorithm SHA256).Hash.ToLowerInvariant() -ne $SpecSHA256){throw 'Saved-grader specification mismatch; no credential entry or call'}
if((Get-FileHash -LiteralPath $OwnerDecision -Algorithm SHA256).Hash.ToLowerInvariant() -ne $OwnerDecisionSHA256){throw 'Saved-grader owner decision mismatch; no credential entry or call'}
$enteredLocally=$false
Push-Location -LiteralPath $appRoot
try {
  $env:PYTHONDONTWRITEBYTECODE='1';$env:PYTHONNOUSERSITE='1'
  # New saved-answer-only purpose, exact source/store, expiry and caps are
  # checked before any credential entry. This performs zero provider calls.
  & $PythonExecutable -B -m research_evaluation.s_qa_saved_grader admit --spec $Specification --spec-pin $SpecSHA256 --store $ClaimStore --approval $OwnerDecision --approval-pin $OwnerDecisionSHA256
  if($LASTEXITCODE -ne 0){throw 'Fresh saved-grader admission failed; no credential entry or call'}
  if(-not $env:NEBIUS_API_KEY){
    Add-Type -AssemblyName System.Windows.Forms
    $dialog=New-Object System.Windows.Forms.Form
    $dialog.Text='SE6 saved answers - private grader-only Nebius entry'
    $dialog.Width=530;$dialog.Height=220;$dialog.StartPosition='CenterScreen';$dialog.TopMost=$true
    $label=New-Object System.Windows.Forms.Label
    $label.Text='Masked, not saved. Only the exact newly approved saved-answer grading batch runs; no reader or key-test call.'
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
  & $PythonExecutable -B -m research_evaluation.s_qa_saved_grader execute --spec $Specification --spec-pin $SpecSHA256 --store $ClaimStore --approval $OwnerDecision --approval-pin $OwnerDecisionSHA256 --live
  exit $LASTEXITCODE
} finally {
  if($enteredLocally){Remove-Item Env:\NEBIUS_API_KEY -ErrorAction SilentlyContinue}
  Pop-Location
}
