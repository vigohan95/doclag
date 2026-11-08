"""Pack finished single cards, not yet assigned, into cards/card_NNN.txt. usage: pack_cards.py <batch_size> [max_batches]"""
import glob, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
O = os.path.join(ROOT, "cards_one")
D = os.path.join(ROOT, "cards")
os.makedirs(D, exist_ok=True)
sp = os.path.join(D, "assigned.txt")
done = set(open(sp).read().split()) if os.path.exists(sp) else set()
files = [f for f in sorted(glob.glob(O + "/*.txt")) if os.path.getsize(f) > 0 and os.path.basename(f)[:-4] not in done]
B = int(sys.argv[1])
M = int(sys.argv[2]) if len(sys.argv) > 2 else 10**6
n0 = len(glob.glob(D + "/card_*.txt"))
made = 0
for i in range(0, len(files), B):
    grp = files[i : i + B]
    if made >= M or len(grp) < max(3, B // 3):
        break
    with open(os.path.join(D, f"card_{n0 + made:03d}.txt"), "w", encoding="utf-8") as f:
        for x in grp:
            f.write(open(x, encoding="utf-8").read() + "\n")
    with open(sp, "a") as f:
        f.write("\n".join(os.path.basename(x)[:-4] for x in grp) + "\n")
    print(f"card_{n0 + made:03d}", len(grp))
    made += 1
print("unassigned left", len(files) - sum(1 for _ in []) - made * B if made else len(files))
