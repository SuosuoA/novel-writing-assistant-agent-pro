"""运行单元测试并生成覆盖率报告"""
import subprocess
import sys

def run_tests():
    """运行测试"""
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/test_core_modules.py",
            "-v",
            "--cov=core",
            "--cov-report=term-missing",
            "--tb=short"
        ],
        cwd=r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro",
        capture_output=True,
        text=True
    )
    
    print("STDOUT:")
    print(result.stdout)
    print("\nSTDERR:")
    print(result.stderr)
    print("\nReturn Code:", result.returncode)
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(run_tests())
