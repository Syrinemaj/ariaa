from app.cleanup.uploaded_files_cleanup import cleanup_upload_directory


def run_upload_cleanup(dry_run: bool = False) -> dict:
    result = cleanup_upload_directory(dry_run=dry_run)

    print("\n================ UPLOAD CLEANUP ================")
    print(f"Directory      : {result.get('directory')}")
    print(f"Deleted files  : {result.get('deleted_count', 0)}")
    print(f"Skipped files  : {result.get('skipped_count', 0)}")
    print(f"Dry run        : {result.get('dry_run')}")
    print("================================================\n")

    return result
