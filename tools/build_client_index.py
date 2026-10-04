"""Индекс архива клиента для проверки и починки файлов игры (clientrepair.py).

Читает RAR5-архив раздачи клиента и пишет content/client-index.json: для каждого файла — размер,
CRC32 и где в архиве лежит его кусок. build_content_manifest.py публикует индекс рядом с manifest2.json.
Перестраивать при каждой новой раздаче клиента (новый архив = новые смещения).

Запуск (из папки launcher/):
    python tools/build_client_index.py --rar D:\\Games\\PLGames_Wow3.3.5.rar
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import clientrepair  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Индекс архива клиента")
    ap.add_argument("--rar", required=True, help="архив раздачи клиента (RAR5)")
    ap.add_argument("--out", default=os.path.join("content", clientrepair.INDEX_NAME))
    args = ap.parse_args(argv)
    index = clientrepair.index_from_rar(args.rar)
    clientrepair.parse_index(index)  # то же, что проверит лаунчер
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    total = sum(f["size"] for f in index["files"])
    print(f"{len(index['files'])} файлов, {total / 2 ** 30:.2f} ГБ, архив {index['archive']} "
          f"({index['archive_size'] / 2 ** 30:.2f} ГБ), папка «{index['root']}» -> {args.out}")


if __name__ == "__main__":
    main()
