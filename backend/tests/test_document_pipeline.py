import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.embedding_client import EmbeddingClient
from app.services.text_splitter import TextBlock, TextSplitter


class DocumentPipelineTest(unittest.TestCase):
    def test_text_splitter_preserves_order_and_offsets(self):
        splitter = TextSplitter(chunk_size=30, overlap=5)
        chunks = splitter.split_blocks(
            [
                TextBlock(
                    text=(
                        "第一段介绍进程拥有独立地址空间。"
                        "第二段介绍线程共享进程资源。"
                        "第三段介绍同步互斥和并发安全。"
                    ),
                    page_no=2,
                )
            ]
        )

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].page_no, 2)
        self.assertLess(chunks[0].start_offset, chunks[0].end_offset)
        self.assertEqual(chunks[1].chunk_index, 1)

    def test_local_embedding_is_deterministic_and_normalized(self):
        client = EmbeddingClient()
        first = client._embed_locally("进程和线程共享资源")
        second = client._embed_locally("进程和线程共享资源")

        self.assertEqual(first, second)
        self.assertEqual(len(first), client.local_dimension)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
