"""Apply the no-embedding adaptation to the pinned upstream source at build time."""
from pathlib import Path
import sys


def patch(root):
    replacements = {
        'src/models/prompter.js': [(
            'if (embedding_model_profile) {\n            this.embedding_model',
            'if (this.profile.embedding === false) {\n'
            '            this.embedding_model = null;\n'
            '        }\n'
            '        else if (embedding_model_profile) {\n            this.embedding_model',
        )],
        'src/agent/library/skill_library.js': [(
            'if (select_num === -1) {\n'
            '            skill_doc_similarities = Object.keys(this.skill_docs_embeddings)\n'
            '            .map(doc_key => ({',
            'if (select_num === -1) {\n'
            '            skill_doc_similarities = this.skill_docs\n'
            '            .map(doc_key => ({',
        ), (
            'skill_doc_similarities = Object.keys(this.skill_docs_embeddings)\n'
            '                .map(doc_key => ({\n'
            '                    doc_key,\n'
            '                    similarity_score: wordOverlapScore(message, this.skill_docs_embeddings[doc_key])',
            'skill_doc_similarities = this.skill_docs\n'
            '                .map(doc_key => ({\n'
            '                    doc_key,\n'
            '                    similarity_score: wordOverlapScore(message, doc_key)',
        )],
    }
    pending = {}
    for filename, changes in replacements.items():
        path = root / filename
        source = path.read_text()
        for old, new in changes:
            if source.count(old) != 1:
                raise RuntimeError(f'Pinned Mindcraft source mismatch: {filename}')
            source = source.replace(old, new, 1)
        pending[path] = source
    for path, source in pending.items():
        path.write_text(source)


if __name__ == '__main__':
    patch(Path(sys.argv[1] if len(sys.argv) > 1 else '/app'))
