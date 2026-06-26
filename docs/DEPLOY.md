# 無料クラウド公開ガイド（フロント＋バックを1サービスで配信）

本アプリは「FastAPI が、ビルド済みフロント(Vite)も同じサーバーから配信する」
構成にしました。デプロイ対象は **Dockerイメージ1つだけ** です。

- `Dockerfile` … フロントをビルド → FastAPI が `/` で配信、`/api` でAPI提供
- `fly.toml` … Fly.io 用（SQLiteを永続ボリュームに保存）
- `render.yaml` … Render 用（無料・ただしDB非永続の注意あり）

---

## おすすめ：Fly.io（データが消えない・実質ゼロ円）

SQLite をそのまま使い、**永続ボリューム**にDBを置くのでデータが消えません。
アイドル時はマシンが停止し、コンピュート課金はほぼ発生しません
（1GBボリュームの保管料が月数円程度）。

```bash
# 1. CLIインストール（初回のみ）
curl -L https://fly.io/install.sh | sh

# 2. ログイン（無料アカウント作成）
fly auth login

# 3. アプリ作成（fly.toml を使う。今はデプロイしない）
cd WH-resource-allocation
fly launch --no-deploy --copy-config --name wh-resource-allocation

# 4. SQLite用の永続ボリュームを作成（東京リージョン）
fly volumes create wh_data --size 1 --region nrt

# 5. デプロイ
fly deploy
```

公開URL: `https://wh-resource-allocation.fly.dev`

> マシンを1台に保つ（ボリュームは1マシンに固定される）。同時アクセスが
> 多くなければこれで十分です。

---

## 代替：Render（完全無料・ただしDBが初期化される点に注意）

GitHub連携でWeb画面からデプロイできます。

1. https://render.com にGitHubでサインアップ
2. New → Blueprint → このリポジトリを選択（`render.yaml` を自動検出）
3. デプロイ完了で `https://<名前>.onrender.com` が発行される

**重要な制約:** 無料プランは永続ディスクが無いため、再デプロイや
スリープ復帰のたびにSQLiteが初期化され、入力した物量計画・最適化結果は
消えます（工程／従業員などのシードデータは毎回復元されます）。
社員マスタを見せるデモ用途なら問題ありませんが、日々の入力を残したい場合は
Fly.io を使ってください。

無料プランは15分アクセスが無いとスリープし、次回アクセスで起動に数十秒かかります。

---

## ローカルでDocker動作確認

```bash
docker build -t wh-app .
docker run -p 8080:8080 -v wh_data:/data wh-app
# → http://localhost:8080
```

---

## アクセス制限したい場合

社内限定で見せたいだけなら、上記URLを共有しつつ、
Fly.io / Render いずれも環境変数や前段の認証（Cloudflare Access 等、無料枠あり）で
簡易的なアクセス制限を追加できます。必要なら設定します。
