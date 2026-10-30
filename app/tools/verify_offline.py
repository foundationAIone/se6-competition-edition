"""Run the complete packaged offline suite with its reviewed native fixture."""
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    env=dict(os.environ)
    env.update({'HOSTED_TEST_COMPETITION_BUNDLE':str(ROOT/'private-native'),
        'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
    return subprocess.call([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider','tests','benchmark/test_public_evidence.py'],cwd=ROOT,env=env)
if __name__=='__main__':raise SystemExit(main())
