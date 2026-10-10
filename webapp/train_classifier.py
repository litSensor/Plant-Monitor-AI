import argparse, json, time
from pathlib import Path
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import datasets, transforms, models

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class WithTransform(Dataset):
    def __init__(self, base, indices, tf):
        self.base = base; self.indices = indices; self.tf = tf
    def __len__(self): return len(self.indices)
    def __getitem__(self, i):
        img, label = self.base[self.indices[i]]
        return self.tf(img), label


def build_loaders(data_dir, batch_size, val_split):
    train_tf = transforms.Compose([
        transforms.Resize(256),
        transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.2, 0.2, 0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    full = datasets.ImageFolder(str(data_dir))
    classes = full.classes
    n_val = max(1, int(len(full) * val_split))
    n_train = len(full) - n_val
    tr_idx, va_idx = torch.utils.data.random_split(
        range(len(full)), [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )
    tr = WithTransform(full, list(tr_idx), train_tf)
    va = WithTransform(full, list(va_idx), val_tf)
    return (DataLoader(tr, batch_size=batch_size, shuffle=True, num_workers=0),
            DataLoader(va, batch_size=batch_size, shuffle=False, num_workers=0),
            classes)


def build_model(n):
    m = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    m.fc = nn.Linear(m.fc.in_features, n)
    return m.to(DEVICE)


def train(a):
    tr, va, classes = build_loaders(Path(a.data_dir), a.batch_size, a.val_split)
    print(f"Классы ({len(classes)}): {classes}", flush=True)
    print(f"Train: {len(tr.dataset)} | Val: {len(va.dataset)}", flush=True)

    model = build_model(len(classes))
    crit = nn.CrossEntropyLoss()
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=a.epochs)

    best = 0.0
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)

    for e in range(1, a.epochs + 1):
        t0 = time.time()
        model.train()
        tl = tc = tt = 0
        for x, y in tr:
            x, y = x.to(DEVICE), y.to(DEVICE)
            opt.zero_grad()
            o = model(x); loss = crit(o, y); loss.backward(); opt.step()
            tl += loss.item() * x.size(0)
            tc += (o.argmax(1) == y).sum().item()
            tt += x.size(0)
        sch.step()

        model.eval()
        vc = vt = 0
        with torch.no_grad():
            for x, y in va:
                x, y = x.to(DEVICE), y.to(DEVICE)
                vc += (model(x).argmax(1) == y).sum().item()
                vt += x.size(0)

        print(f"[{e:02d}/{a.epochs}] loss={tl/max(1,tt):.4f} "
              f"train={tc/max(1,tt):.3f} val={vc/max(1,vt):.3f} ({time.time()-t0:.1f}s)",
              flush=True)
        if vt and vc/vt >= best:
            best = vc/vt
            torch.save(model.state_dict(), out)
            print(f"  ↳ сохранено (val={best:.3f})", flush=True)

    out.with_suffix(".classes.json").write_text(
        json.dumps(classes, ensure_ascii=False, indent=2))
    print(f"\nГотово. Best val={best:.3f}")
    print(f"Веса:   {out}")
    print(f"Классы: {out.with_suffix('.classes.json')}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default="webapp/training_data")
    p.add_argument("--out", default="webapp/models/plant_classifier.pth")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--val-split", type=float, default=0.2)
    train(p.parse_args())
