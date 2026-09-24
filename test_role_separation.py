import ast, unittest
from pathlib import Path

SRC=(Path(__file__).resolve().parent/'app.py').read_text()
TREE=ast.parse(SRC)

def function_source(name):
    node=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name==name)
    return ast.get_source_segment(SRC,node) or ''

class RoleSeparationTests(unittest.TestCase):
    def test_primary_stage3_wake_uses_shared_lock_path(self):
        s=function_source('wake')
        self.assertNotIn("status='STAGE2_PRIMARY_RESERVED'",s)
        self.assertIn('start_or_extend',s)

    def test_primary_cron_wake_uses_shared_stage3_path(self):
        s=function_source('cron_wake')
        self.assertNotIn("status='STAGE2_PRIMARY_IDLE'",s)
        self.assertIn("start_or_extend('EXTERNAL_CRON')",s)

    def test_primary_rejects_stage3_sync_tick(self):
        s=function_source('tick')
        self.assertIn('if STAGE2_PRIMARY_ROLE',s)
        self.assertIn("status='STAGE2_PRIMARY_RESERVED'",s)
        self.assertLess(s.index("status='STAGE2_PRIMARY_RESERVED'"),s.index('_note_browser_demand'))

    def test_stage3_shard_rejects_stage2_wake(self):
        s=function_source('stage2_wake')
        self.assertIn('if not STAGE2_PRIMARY_ROLE',s)
        self.assertIn("status='STAGE3_BROWSER_RESERVED'",s)
        self.assertLess(s.index("status='STAGE3_BROWSER_RESERVED'"),s.index("request.get_json"))

if __name__=='__main__':
    unittest.main()
