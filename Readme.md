# CGA crawler

海巡署網頁爬蟲；本程式系依業務需求建立，用於爬取本署公開網頁資訊。


## 環境需求

* Python >= 3.6
* [pipenv](https://pipenv.readthedocs.io/en/latest/)

安裝相依函式庫

```bash
pipenv install
```


## 執行

預設參數為爬取艦隊分署網頁，並將結果存在 `site.csv` 中

```bash
python get_list.py
```

或以以下格式讀取特定分署網頁（理論可行，未驗證）

```bash
python get_list.py --url <SITEMAP> --output <FILE>
```

其中 `<SITEMAP>` 應代入該分署 *網站導覽* 頁面網址，而 `<FILE>` 應代入儲存的檔案位置（無論副檔名為何，將以csv格式輸出）
