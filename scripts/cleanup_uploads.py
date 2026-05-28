from app.cleanup.service import run_upload_cleanup


def main() -> None:
    run_upload_cleanup(dry_run=False)


if __name__ == "__main__":
    main()
