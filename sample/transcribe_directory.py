import json
import os
import sys
import time
import traceback
from speechkitty import Directory, Transcriber, Parser


def main():
    try:
        rec_dir = sys.argv[1]
        aws_access_key_id = str(os.environ.get("AWS_ACCESS_KEY_ID"))
        aws_secret_access_key = str(os.environ.get("AWS_SECRET_ACCESS_KEY"))
        storage_bucket_name = str(os.environ.get("STORAGE_BUCKET_NAME"))
        transcribe_api_key = str(os.environ.get("TRANSCRIBE_API_KEY"))
        language_code = str(os.environ.get("LANGUAGE_CODE"))
    except Exception:
        print("Not enough arguments.")
        return 1

    try:
        filename_hash_func = str(sys.argv[2])
    except Exception:
        filename_hash_func = ""

    # This is business specific, delete it from your production code
    exclude = "^.+(:?-in|-out)\\.wav$"

    # Set up directory
    directory = Directory(rec_dir)

    # Find files recursively
    wavs = directory.get_wavs(regexp_exclude=exclude, skip_processed=True)

    # This is business specific, delete it from your production code
    for i in range(len(wavs)):
        if "wav-mix" in wavs[i]:
            new = wavs[i].replace(".wav-mix", "")
            os.rename(wavs[i], new)
            wavs[i] = new

    # If there're no files found just exit silently
    if not wavs:
        return

    wavs = list(set(wavs))

    # If you want to limit number of records processed
    # wavs = random.choices(wavs, k=min(len(wavs), 10))

    transcriber = Transcriber(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        storage_bucket_name=storage_bucket_name,
        transcribe_api_key=transcribe_api_key,
        language_code=language_code,
    )
    parser = Parser()

    for wav_path in wavs:
        # Convert wav to ogg
        ogg_path = transcriber.wav_to_ogg(wav_path)
        # If there's an error converting file
        if ogg_path is None:
            # Create empty json to skip the wav during next runs
            json_path = wav_path[:-4] + ".json"
            with open(json_path, "w") as f:
                f.write("")
            continue

        # Upload ogg to object storage
        ogg_link = transcriber.upload_ogg(ogg_path)

        # If upload ends with error
        if ogg_link is None:
            continue

        # Start transcribing task
        id = transcriber.submit_task(ogg_link)

        result = ""
        # Limit number of attempts to get result
        for i in range(100):
            time.sleep(3)
            result = transcriber.get_result(id)
            # If there's an error, stop trying
            try:
                if result["done"]:
                    break
            except Exception:
                break

        if len(result) == 0:
            continue

        # Delete ogg from temp_dir and object storage
        transcriber.delete_ogg(ogg_path)

        # Compose resulting json path
        json_path = wav_path[:-4] + ".json"
        with open(json_path, "w") as f:
            f.write(json.dumps(result, ensure_ascii=False))

        # Parse json into pandas dataframe
        try:
            df = parser.parse_result(result)
        except Exception:
            print("exception in parse_result():", wav_path)
            print(traceback.format_exc())
            continue
        # Create html table
        if df is None:
            continue
        html = parser.create_html(df)
        html_path = parser.name_html(wav_path, hash_func=filename_hash_func)
        # Write table
        with open(html_path, "w") as f:
            f.write(html)


if __name__ == "__main__":
    main()