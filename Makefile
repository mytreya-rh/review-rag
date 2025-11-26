init:
python -c "import os; os.makedirs('data', exist_ok=True)"
psql "$(PGVECTOR_URL)" -f sql/schema.sql


collect:
python src/github_collect.py $(REPO) $(PR)


preprocess:
python src/arch_preprocess.py data/pr_records.jsonl


embed:
python src/embed_store.py


distill:
python src/distill_guidelines.py


review:
python src/review_cli.py $(DIFF)
