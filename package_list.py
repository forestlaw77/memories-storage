import subprocess
import json

# pip list を JSON 形式で取得
result = subprocess.run(
    ["pip", "list", "--format=json"], capture_output=True, text=True
)
packages = json.loads(result.stdout)

# テーブルのヘッダー
markdown_table = "| パッケージ名 | バージョン | ライセンス | サマリ |\n|-------------|----------|---------|--------|\n"

for package in packages:
    # 各パッケージの詳細を取得
    package_info = subprocess.run(
        ["pip", "show", package["name"]], capture_output=True, text=True
    )
    info_lines = package_info.stdout.split("\n")
    info_dict = {
        line.split(": ")[0]: line.split(": ")[1] for line in info_lines if ": " in line
    }

    # 必要な情報を取得
    name = package["name"]
    version = package["version"]
    license = info_dict.get("License", "不明")
    summary = info_dict.get("Summary", "なし")

    # Markdown のテーブルに追加
    markdown_table += f"| {name} | {version} | {license} | {summary} |\n"

print(markdown_table)
