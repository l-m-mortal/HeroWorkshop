import SwiftUI
import UniformTypeIdentifiers

// MARK: - State produced by `python3 workshop.py state`

struct Resolved: Codable, Hashable {
    var source: String            // map | disk | standard | missing | none
    var path: String?
    var preview: String?
    enum CodingKeys: String, CodingKey { case source = "where", path, preview }
}
struct Override: Codable, Hashable {
    var source: String
    var target: String
    enum CodingKeys: String, CodingKey { case source = "where", target, source_file = "source", applied }
    var source_file: String?
    var applied: String?
}
struct IconInfo: Codable, Hashable {
    var art: String?
    var art_file: String?
    var normal: Resolved
    var disabled: Resolved
    var override: Override?
}
struct Dota2Ref: Codable, Hashable {
    var key: String?
    var name: String
    var img: String?
}
struct Ability: Codable, Hashable, Identifiable {
    var code: String
    var name: String
    var hero: Bool
    var buttonpos: [Int]?
    var researchpos: [Int]?
    var icon: IconInfo
    var dota2: Dota2Ref?
    var id: String { code }
    var visible: Bool { icon.art != nil || buttonpos != nil }
    /// Dota 2 name, shown only when it differs from the in-map name (used next to command-card slots).
    var dota2NoteIfDifferent: String? {
        guard let d = dota2, d.name != name else { return nil }
        return d.name
    }
}
struct SavedScales: Codable, Hashable { var scale: Double?; var morph: Double?; var alt: Double?; var applied: String? }
struct RelatedUnit: Codable, Hashable, Identifiable {
    var code: String
    var relation: String
    var name: String
    var model: String?
    var scale: Double?
    var p3_scale: Double?
    var saved_scales: SavedScales?
    var icon: IconInfo
    var abilities: [Ability]
    var dota2: Dota2Ref?             // unused in the UI so far, kept for forward compatibility
    var id: String { code }
}
struct Hero: Codable, Hashable, Identifiable {
    var code: String
    var name: String
    var txt_name: String?
    var model: String?
    var scale: Double?
    var p3_scale: Double?
    var alt: String?
    var alt_scale: Double?
    var saved_scales: SavedScales?
    var icon: IconInfo
    var abilities: [Ability]
    var dota2: Dota2Ref?
    var extra_abilities: [Ability]?
    var forms: [RelatedUnit]?
    var summons: [RelatedUnit]?
    var tavern: RelatedUnit?
    var related: [RelatedUnit]?     // kept for backward compatibility with older state.json files; not used in the UI anymore
    var group: String?              // hero | other
    var id: String { code }
}
struct ShopUnit: Codable, Hashable, Identifiable {
    var code: String
    var shop: String
    var shop_name: String
    var index: Int
    var buttonpos: [Int]?
    var icon: IconInfo
    var id: String { code + shop + String(index) }
}
struct Shop: Codable, Hashable, Identifiable {
    var code: String
    var name: String
    var units: [String]
    var id: String { code }
}
struct ItemVariant: Codable, Hashable, Identifiable {
    var art: String?
    var names: [String]
    var codes: [String]
    var label: String
    var keys: String
    var icon: IconInfo
    var id: String { keys }
}
struct Item: Codable, Hashable, Identifiable {
    var code: String?
    var name: String
    var names: [String]?
    var codes: [String]
    var keys: String                // "unit:X,item:A,item:B" — every rawcode this drop must apply to
    var count: Int
    var distinct_arts: Int
    var icon: IconInfo               // what the shop card shows (dummy-unit icon)
    var icon_item: IconInfo?         // what the hero inventory shows (item icon), if different in the data
    var in_shops: [String]?
    var shop_units: [ShopUnit]
    var variants: [ItemVariant]
    var id: String { name }

    enum CodingKeys: String, CodingKey { case code, name, names, codes, keys, count, distinct_arts, icon, icon_item, in_shops, shop_units, variants }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        code = try c.decodeIfPresent(String.self, forKey: .code)
        name = try c.decode(String.self, forKey: .name)
        names = try c.decodeIfPresent([String].self, forKey: .names)
        codes = try c.decode([String].self, forKey: .codes)
        keys = try c.decode(String.self, forKey: .keys)
        count = try c.decode(Int.self, forKey: .count)
        distinct_arts = try c.decode(Int.self, forKey: .distinct_arts)
        icon = try c.decode(IconInfo.self, forKey: .icon)
        icon_item = try c.decodeIfPresent(IconInfo.self, forKey: .icon_item)
        in_shops = try c.decodeIfPresent([String].self, forKey: .in_shops)
        shop_units = try c.decodeIfPresent([ShopUnit].self, forKey: .shop_units) ?? []
        variants = try c.decodeIfPresent([ItemVariant].self, forKey: .variants) ?? []
    }
}
struct Candidate: Codable, Hashable, Identifiable {
    var file: String
    var preview: String
    var set: String
    var source: String
    var how: String
    var id: String { file }
}
struct CommonIcon: Codable, Hashable, Identifiable {
    var key: String
    var name: String
    var base: String
    var icon: IconInfo
    var id: String { key }
}
struct MapState: Codable {
    var map: String
    var game_root: String
    var generated: String
    var work_dir: String
    var heroes: [Hero]
    var items: [Item]
    var shops: [Shop]?
    var common: [CommonIcon]?
}

// MARK: - Store

@MainActor final class Store: ObservableObject {
    @Published var state: MapState?
    @Published var status = "Загрузка состояния карты…"
    @Published var busy = false
    @Published var showDisabled = false
    let root: URL

    init() {
        root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        refresh()
    }

    var mapName: String { state.map { URL(fileURLWithPath: $0.map).lastPathComponent } ?? "—" }

    func previewURL(_ res: Resolved) -> URL? {
        guard let p = res.preview, let work = state?.work_dir else { return nil }
        return URL(fileURLWithPath: work).appendingPathComponent(p)
    }

    /// Runs workshop.py with the given arguments off the main thread, then calls back on the main actor.
    func run(_ args: [String], then: @escaping @MainActor @Sendable (Int32, String) -> Void) {
        busy = true
        let root = self.root
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["python3", "workshop.py"] + args
            process.currentDirectoryURL = root
            let pipe = Pipe(); process.standardOutput = pipe; process.standardError = pipe
            var output = ""; var code: Int32 = -1
            do {
                try process.run()
                output = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
                process.waitUntilExit(); code = process.terminationStatus
            } catch { output = error.localizedDescription }
            let rc = code, text = output.trimmingCharacters(in: .whitespacesAndNewlines)
            Task { @MainActor in then(rc, text) }
        }
    }

    func refresh(message: String? = nil) {
        run(["state"]) { code, out in
            defer { self.busy = false }
            guard code == 0, let path = out.split(separator: "\n").last else { self.status = "Ошибка: \(out)"; return }
            do {
                let data = try Data(contentsOf: URL(fileURLWithPath: String(path)))
                self.state = try JSONDecoder().decode(MapState.self, from: data)
                self.status = message ?? "Карта: \(self.mapName) · героев \(self.state!.heroes.count) · предметов \(self.state!.items.count)"
            } catch { self.status = "Не удалось прочитать состояние: \(error.localizedDescription)" }
        }
    }

    func setIcon(key: String, file: URL) {
        let ext = file.pathExtension.lowercased()
        guard ["png", "blp", "bmp", "tga", "jpg", "jpeg"].contains(ext) else { status = "Нужен PNG или BLP (можно BMP/TGA/JPG)"; return }
        status = "Применяю \(file.lastPathComponent) → \(key)…"
        run(["set-icon", key, file.path]) { code, out in
            if code == 0 { self.refresh(message: out.split(separator: "\n").last.map(String.init) ?? "Готово") }
            else { self.busy = false; self.status = "Ошибка: \(out)" }
        }
    }
    func clearIcon(key: String) {
        run(["clear-icon", key]) { code, out in
            if code == 0 { self.refresh(message: "Возвращена исходная иконка: \(key)") } else { self.busy = false; self.status = "Ошибка: \(out)" }
        }
    }
    func setScale(hero: Hero, scale: Double, morph: Double?, alt: Double?) {
        var args = ["set-scale", hero.code, String(format: "%.3f", scale)]
        if let morph { args += ["--morph", String(format: "%.3f", morph)] }
        if let alt, hero.alt != nil { args += ["--alt", String(format: "%.3f", alt)] }
        run(args) { code, out in
            if code == 0 { self.refresh(message: out.split(separator: "\n").last.map(String.init) ?? "Масштаб применён") } else { self.busy = false; self.status = "Ошибка: \(out)" }
        }
    }
    func setScale(code: String, scale: Double) {
        run(["set-scale", code, String(format: "%.3f", scale)]) { rc, out in
            if rc == 0 { self.refresh(message: out.split(separator: "\n").last.map(String.init) ?? "Масштаб применён") } else { self.busy = false; self.status = "Ошибка: \(out)" }
        }
    }
    func addRelated(hero: String, unit: String) {
        run(["add-related", hero, unit]) { rc, out in
            if rc == 0 { self.refresh(message: out) } else { self.busy = false; self.status = "Ошибка: \(out)" }
        }
    }
    func removeRelated(hero: String, unit: String) {
        run(["remove-related", hero, unit]) { rc, out in
            if rc == 0 { self.refresh(message: out) } else { self.busy = false; self.status = "Ошибка: \(out)" }
        }
    }
    func candidates(for key: String, then: @escaping @MainActor @Sendable ([Candidate]) -> Void) {
        run(["candidates", key]) { code, out in
            self.busy = false
            guard code == 0, let data = out.data(using: .utf8),
                  let list = try? JSONDecoder().decode([Candidate].self, from: data) else { then([]); return }
            then(list)
        }
    }
}

// MARK: - HUD colours

enum HUD {
    static let stone = LinearGradient(colors: [Color(red: 0.16, green: 0.17, blue: 0.19), Color(red: 0.08, green: 0.09, blue: 0.10)], startPoint: .top, endPoint: .bottom)
    static let panel = Color(red: 0.11, green: 0.12, blue: 0.13)
    static let gold = Color(red: 0.82, green: 0.66, blue: 0.28)
    static let slot = Color(red: 0.04, green: 0.04, blue: 0.05)
}

// MARK: - Icon slot (drop target)

struct IconSlot: View {
    @ObservedObject var store: Store
    let key: String
    let title: String
    let subtitle: String
    let icon: IconInfo
    var size: CGFloat = 64
    var note: String? = nil
    var forceDisabled: Bool? = nil
    @State private var targeted = false
    @State private var importing = false
    @State private var pickerOpen = false
    @State private var candidateList: [Candidate] = []
    @State private var candidatesLoading = false

    func openPicker() {
        pickerOpen = true
        candidatesLoading = true
        store.candidates(for: key) { list in
            self.candidateList = list
            self.candidatesLoading = false
        }
    }

    var resolved: Resolved { (forceDisabled ?? store.showDisabled) ? icon.disabled : icon.normal }
    var originText: String {
        switch resolved.source {
        case "map": return "в карте"
        case "disk": return "на диске"
        case "standard": return "стандарт WC3"
        case "missing": return "файл не найден"
        default: return "нет иконки"
        }
    }
    var body: some View {
        VStack(spacing: 3) {
            ZStack {
                RoundedRectangle(cornerRadius: 4).fill(HUD.slot)
                if let url = store.previewURL(resolved), let image = NSImage(contentsOf: url) {
                    Image(nsImage: image).resizable().interpolation(.none).frame(width: size - 6, height: size - 6).cornerRadius(3)
                } else {
                    VStack(spacing: 2) {
                        Image(systemName: resolved.source == "standard" ? "shield.lefthalf.filled" : "questionmark.square.dashed").foregroundStyle(.secondary)
                        if resolved.source == "standard" { Text("WC3").font(.system(size: 8)).foregroundStyle(.secondary) }
                    }
                }
                if icon.override != nil {
                    Circle().fill(Color.green).frame(width: 9, height: 9).overlay(Circle().stroke(.black, lineWidth: 1))
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing).padding(3)
                }
            }
            .frame(width: size, height: size)
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(targeted ? Color.green : HUD.gold.opacity(0.55), lineWidth: targeted ? 2 : 1))
            .onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
                guard let provider = providers.first else { return false }
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { value, _ in
                    if let data = value as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) {
                        Task { @MainActor in store.setIcon(key: key, file: url) }
                    }
                }
                return true
            }
            .onTapGesture(count: 2) { importing = true }
            .onTapGesture(count: 1) { openPicker() }
            .contextMenu {
                Button("Выбрать файл…") { importing = true }
                Button("Выбрать из библиотеки…") { openPicker() }
                if icon.override != nil { Button("Вернуть исходную иконку") { store.clearIcon(key: key) } }
                if let path = resolved.path, resolved.source == "disk" {
                    Button("Показать файл в Finder") {
                        let url = URL(fileURLWithPath: store.state?.game_root ?? "/").appendingPathComponent(path.replacingOccurrences(of: "\\", with: "/"))
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                }
            }
            .help("\(title)\n\(subtitle)\nПуть: \(icon.art ?? "—")\nИсточник: \(originText)" + (icon.override.map { "\nЗаменена: \($0.applied ?? "")" } ?? ""))
            .fileImporter(isPresented: $importing, allowedContentTypes: [.png, .bmp, .jpeg, UTType(filenameExtension: "blp") ?? .data, UTType(filenameExtension: "tga") ?? .data]) { result in
                if case let .success(url) = result { store.setIcon(key: key, file: url) }
            }
            .popover(isPresented: $pickerOpen) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Выбор иконки: \(title)").font(.headline)
                    if candidatesLoading {
                        HStack { ProgressView().controlSize(.small); Text("Загружаю варианты…") }
                            .frame(width: 340, height: 100)
                    } else if candidateList.isEmpty {
                        Text("Библиотека пуста: соберите её командой python3 library_build.py")
                            .font(.callout).foregroundStyle(.secondary)
                            .frame(width: 340, height: 100)
                    } else {
                        ScrollView {
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 74), spacing: 10)], spacing: 12) {
                                ForEach(candidateList) { c in
                                    Button {
                                        store.setIcon(key: key, file: URL(fileURLWithPath: c.file))
                                        pickerOpen = false
                                    } label: {
                                        VStack(spacing: 3) {
                                            if let img = NSImage(contentsOf: URL(fileURLWithPath: c.preview)) {
                                                Image(nsImage: img).resizable().interpolation(.none).frame(width: 64, height: 64).cornerRadius(3)
                                            } else {
                                                RoundedRectangle(cornerRadius: 4).fill(HUD.slot).frame(width: 64, height: 64)
                                            }
                                            Text(c.set).font(.system(size: 8)).lineLimit(1).frame(width: 70)
                                        }
                                    }
                                    .buttonStyle(.plain)
                                    .help(c.source)
                                }
                            }
                            .padding(10)
                        }
                        .frame(width: 380, height: 320)
                    }
                }
                .padding(10)
            }
            Text(title).font(.system(size: 10)).lineLimit(1).frame(width: size + 14)
            Text(originText).font(.system(size: 8)).foregroundStyle(icon.override != nil ? Color.green : Color.secondary).lineLimit(1)
            if let note {
                Text(note).font(.system(size: 8)).foregroundStyle(.secondary).lineLimit(1).frame(width: size + 14)
            }
        }
    }
}

// MARK: - Command card layout (4×3, by in-game Buttonpos; extra abilities go to the overflow row)

func commandGrid(_ abilities: [Ability]) -> [[Ability?]] {
    var cells: [[Ability?]] = Array(repeating: Array(repeating: nil, count: 4), count: 3)
    var rest: [Ability] = []
    for a in abilities where a.visible {
        if let p = a.buttonpos, p.count == 2, (0..<4).contains(p[0]), (0..<3).contains(p[1]), cells[p[1]][p[0]] == nil { cells[p[1]][p[0]] = a }
        else { rest.append(a) }
    }
    for a in rest {
        var placed = false
        for y in 0..<3 where !placed { for x in 0..<4 where cells[y][x] == nil && !placed { cells[y][x] = a; placed = true } }
    }
    return cells
}
func gridOverflow(_ abilities: [Ability]) -> [Ability] {
    let placed = Set(commandGrid(abilities).flatMap { $0 }.compactMap { $0?.code })
    return abilities.filter { $0.visible && !placed.contains($0.code) }
}

struct CommandCard: View {
    @ObservedObject var store: Store
    let abilities: [Ability]
    var body: some View {
        let grid = commandGrid(abilities)
        VStack(spacing: 8) {
            ForEach(0..<3, id: \.self) { y in
                HStack(spacing: 8) {
                    ForEach(0..<4, id: \.self) { x in
                        if let a = grid[y][x] {
                            IconSlot(store: store, key: "ability:\(a.code)", title: a.name, subtitle: "Способность \(a.code)" + (a.hero ? " (геройская)" : ""), icon: a.icon, note: a.dota2NoteIfDifferent)
                        } else {
                            RoundedRectangle(cornerRadius: 4).fill(HUD.slot.opacity(0.6)).frame(width: 64, height: 64)
                                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.white.opacity(0.08)))
                                .frame(width: 78, height: 88, alignment: .top)
                        }
                    }
                }
            }
        }
        .padding(10).background(HUD.stone, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(HUD.gold.opacity(0.4)))
    }
}

struct RelatedUnitCard: View {
    @ObservedObject var store: Store
    let hero: Hero
    let unit: RelatedUnit
    @State private var scale: Double
    init(store: Store, hero: Hero, unit: RelatedUnit) {
        self.store = store; self.hero = hero; self.unit = unit
        _scale = State(initialValue: unit.saved_scales?.scale ?? unit.scale ?? 1.0)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(unit.name).font(.headline); Text("[\(unit.code)]").foregroundStyle(.secondary)
                Text("· \(unit.relation)").font(.caption).foregroundStyle(HUD.gold)
                Spacer()
                if unit.relation.hasPrefix("добавлен") {
                    Button("Убрать") { store.removeRelated(hero: hero.code, unit: unit.code) }.controlSize(.small)
                }
            }
            HStack(alignment: .top, spacing: 14) {
                IconSlot(store: store, key: "unit:\(unit.code)", title: unit.name, subtitle: "Иконка юнита", icon: unit.icon, size: 64)
                VStack(alignment: .leading, spacing: 6) {
                    if unit.relation.hasPrefix("юнит в таверне") {
                        Text("Масштаб как у героя: \(unit.scale.map { $0.formatted() } ?? "—")").font(.caption).foregroundStyle(.secondary)
                    } else {
                        HStack {
                            Text("Масштаб").font(.callout)
                            TextField("1.0", value: $scale, format: .number.precision(.fractionLength(2))).frame(width: 64)
                            Stepper("", value: $scale, in: 0.1...5.0, step: 0.05).labelsHidden()
                            Button("Применить") { store.setScale(code: unit.code, scale: scale) }.controlSize(.small).disabled(store.busy)
                        }
                        Text("в карте \(unit.scale.map { $0.formatted() } ?? "—")" + (unit.p3_scale.map { " · P3 \($0.formatted())" } ?? "")).font(.caption2).foregroundStyle(.secondary)
                    }
                    if let m = unit.model { Text(m).font(.caption2).foregroundStyle(.secondary).lineLimit(1).textSelection(.enabled) }
                }
                if unit.abilities.contains(where: { $0.visible }) {
                    CommandCard(store: store, abilities: unit.abilities)
                } else {
                    Text("Способности те же, что у героя").font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .padding(10).background(HUD.panel, in: RoundedRectangle(cornerRadius: 10))
    }
}

// MARK: - Hero console

struct HeroConsole: View {
    @ObservedObject var store: Store
    let hero: Hero
    @State private var scale: Double
    @State private var alt: Double
    @State private var relatedCode = ""

    init(store: Store, hero: Hero) {
        self.store = store; self.hero = hero
        _scale = State(initialValue: hero.saved_scales?.scale ?? hero.scale ?? 1.0)
        _alt = State(initialValue: hero.saved_scales?.alt ?? hero.alt_scale ?? 1.0)
    }

    var grid: [[Ability?]] { commandGrid(hero.abilities) }
    var overflow: [Ability] { gridOverflow(hero.abilities) }
    var hidden: [Ability] { hero.abilities.filter { !$0.visible } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                // 1. Header: name, code, txt name, Dota 2 label, DISBTN toggle, model line.
                VStack(alignment: .leading, spacing: 2) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(hero.name).font(.title.bold())
                        Text("[\(hero.code)]").foregroundStyle(.secondary)
                        if let t = hero.txt_name, t != hero.name { Text("· \(t)").foregroundStyle(.secondary) }
                        Spacer()
                        Toggle("Серые (DISBTN)", isOn: $store.showDisabled).toggleStyle(.switch).controlSize(.small)
                    }
                    if let d = hero.dota2 { Text("Dota 2: \(d.name)").font(.caption).foregroundStyle(.secondary) }
                }
                if let model = hero.model { Text("Модель: \(model)").font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }

                // 2. The in-game bottom console: portrait | info + scales | command card
                HStack(alignment: .top, spacing: 18) {
                    VStack(spacing: 6) {
                        Text("Портрет / иконка").font(.caption).foregroundStyle(HUD.gold)
                        IconSlot(store: store, key: "unit:\(hero.code)", title: hero.name, subtitle: "Иконка героя (Art юнита)", icon: hero.icon, size: 96)
                    }
                    scaleBox
                    VStack(spacing: 6) {
                        Text("Панель команд").font(.caption).foregroundStyle(HUD.gold)
                        CommandCard(store: store, abilities: hero.abilities)
                    }
                }
                .padding(14).background(HUD.panel, in: RoundedRectangle(cornerRadius: 12))

                if !overflow.isEmpty {
                    Text("Способности без места на панели").font(.headline)
                    LazyVGrid(columns: Array(repeating: GridItem(.fixed(84)), count: 8), spacing: 10) {
                        ForEach(overflow) { a in
                            IconSlot(store: store, key: "ability:\(a.code)", title: a.name, subtitle: "Способность \(a.code)", icon: a.icon, note: a.dota2NoteIfDifferent)
                        }
                    }
                }

                // 3. Extra abilities: hero's own abilities that live elsewhere in the map (Invoker's spells, etc.)
                if let extra = hero.extra_abilities, !extra.isEmpty {
                    Text("Дополнительные способности").font(.headline)
                    LazyVGrid(columns: Array(repeating: GridItem(.fixed(84)), count: 8), spacing: 10) {
                        ForEach(extra) { a in
                            IconSlot(store: store, key: "ability:\(a.code)", title: a.name, subtitle: "Способность \(a.code)" + (a.hero ? " (геройская)" : ""), icon: a.icon, note: a.dota2?.name)
                        }
                    }
                }

                // 4. Hero forms / alternative variants
                if let forms = hero.forms, !forms.isEmpty {
                    Text("Формы героя").font(.headline)
                    ForEach(forms) { unit in RelatedUnitCard(store: store, hero: hero, unit: unit) }
                }

                // 5. Summoned units, plus the always-available "add related unit" row for trigger-made summons.
                if let summons = hero.summons, !summons.isEmpty {
                    Text("Призванные существа").font(.headline)
                    ForEach(summons) { unit in RelatedUnitCard(store: store, hero: hero, unit: unit) }
                }
                HStack {
                    TextField("Rawcode юнита, например n0EE", text: $relatedCode).frame(width: 220)
                    Button("Добавить связанный юнит") {
                        store.addRelated(hero: hero.code, unit: relatedCode.trimmingCharacters(in: .whitespaces)); relatedCode = ""
                    }.disabled(relatedCode.trimmingCharacters(in: .whitespaces).count != 4 || store.busy)
                    Text("Для призывов, которые создаются триггером и не видны в данных способности.").font(.caption2).foregroundStyle(.secondary)
                }

                // 6. Tavern pick unit note
                if let tavern = hero.tavern {
                    Text("Юнит таверны выбора \(tavern.code) получает масштаб героя автоматически.").font(.caption).foregroundStyle(.secondary)
                }

                // 7. Hidden/service abilities + footer hint
                if !hidden.isEmpty {
                    DisclosureGroup("Скрытые / служебные способности (\(hidden.count))") {
                        Text(hidden.map { "\($0.code) \($0.name)" }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                }
                Text("Перетащите PNG или BLP на любую ячейку: файл сразу конвертируется в BLP 64×64, серая версия создаётся автоматически и всё записывается в карту или в папку мода по текущему пути иконки.")
                    .font(.footnote).foregroundStyle(.secondary)
            }.padding()
        }
    }

    var scaleBox: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Масштаб модели").font(.caption).foregroundStyle(HUD.gold)
            scaleRow("Основная", value: $scale, current: hero.scale, extra: hero.p3_scale.map { "P3 \($0.formatted())" })
            if let a = hero.alt { scaleRow("Альтернатива \(a)", value: $alt, current: hero.alt_scale, extra: nil) }
            HStack {
                Button("Применить масштаб") {
                    store.setScale(hero: hero, scale: scale, morph: nil, alt: hero.alt != nil ? alt : nil)
                }.buttonStyle(.borderedProminent).disabled(store.busy)
                if let saved = hero.saved_scales?.applied { Text("сохранено \(saved)").font(.caption2).foregroundStyle(.secondary) }
            }
            Text("Значение абсолютное: 1.20 записывает ровно 1.20 в unitUI и в таблицу P3, поэтому масштаб переживает смерть героя. Юнит таверны выбора получает тот же масштаб автоматически.")
                .font(.caption2).foregroundStyle(.secondary).frame(width: 230)
        }
        .padding(10).background(HUD.stone, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(HUD.gold.opacity(0.4)))
    }
    func scaleRow(_ label: String, value: Binding<Double>, current: Double?, extra: String?) -> some View {
        HStack {
            Text(label).frame(width: 110, alignment: .leading).font(.callout)
            TextField("1.0", value: value, format: .number.precision(.fractionLength(2))).frame(width: 64)
            Stepper("", value: value, in: 0.1...5.0, step: 0.05).labelsHidden()
            VStack(alignment: .leading, spacing: 0) {
                Text("в карте \(current.map { $0.formatted() } ?? "—")").font(.caption2).foregroundStyle(.secondary)
                if let extra { Text(extra).font(.caption2).foregroundStyle(.secondary) }
            }
        }
    }
}

// MARK: - Common icons (command card buttons shared by every unit, plus Attribute Bonus)

struct CommonIconsView: View {
    @ObservedObject var store: Store
    var common: [CommonIcon] { store.state?.common ?? [] }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .firstTextBaseline) {
                    Text("Общие иконки").font(.title.bold())
                    Spacer()
                    Toggle("Серые (DISBTN)", isOn: $store.showDisabled).toggleStyle(.switch).controlSize(.small)
                }
                Text("Кнопки команд, одинаковые у всех юнитов, и плюс к атрибутам. Файл кладётся в карту по стандартному пути и подменяет иконку игры.")
                    .font(.caption).foregroundStyle(.secondary)

                LazyVGrid(columns: Array(repeating: GridItem(.fixed(84)), count: 6), spacing: 10) {
                    ForEach(common) { c in
                        IconSlot(store: store, key: c.key, title: c.name, subtitle: "Путь: \(c.icon.art ?? "—")", icon: c.icon, size: 64)
                    }
                }

                Text("Перетащите PNG или BLP на любую ячейку: файл сразу конвертируется в BLP 64×64, серая версия создаётся автоматически и всё записывается в карту или в папку мода по текущему пути иконки.")
                    .font(.footnote).foregroundStyle(.secondary)
            }.padding()
        }
    }
}

// MARK: - Items / shops

/// One filled cell of a shop's 4×3 command card: the dummy unit sold there and the item it drops.
struct ShopSlot: Identifiable {
    var id: String   // unit code + a disambiguator, unique within one shop's grid
    var unit: ShopUnit
    var item: Item
}

/// Lays out a shop's units exactly like the in-game shop card: by `buttonpos` where known, then by shop order.
func shopGrid(shop: Shop, items: [Item]) -> [[ShopSlot?]] {
    var cells: [[ShopSlot?]] = Array(repeating: Array(repeating: nil, count: 4), count: 3)
    var pairs: [(unit: ShopUnit, item: Item)] = []
    for code in shop.units {
        guard let item = items.first(where: { it in it.shop_units.contains { $0.code == code && $0.shop == shop.code } }),
              let unit = item.shop_units.first(where: { $0.code == code && $0.shop == shop.code }) else { continue }
        pairs.append((unit, item))
    }
    var rest: [(unit: ShopUnit, item: Item)] = []
    for (i, pair) in pairs.enumerated() {
        if let p = pair.unit.buttonpos, p.count == 2, (0..<4).contains(p[0]), (0..<3).contains(p[1]), cells[p[1]][p[0]] == nil {
            cells[p[1]][p[0]] = ShopSlot(id: "\(pair.unit.code)#\(i)", unit: pair.unit, item: pair.item)
        } else {
            rest.append(pair)
        }
    }
    for (i, pair) in rest.enumerated() {
        var placed = false
        for y in 0..<3 where !placed {
            for x in 0..<4 where cells[y][x] == nil && !placed { cells[y][x] = ShopSlot(id: "\(pair.unit.code)#rest\(i)", unit: pair.unit, item: pair.item); placed = true }
        }
    }
    return cells
}

/// Shop card, laid out like `CommandCard`: one IconSlot per sold unit, keyed so a drop updates the shop unit
/// and every inventory rawcode of the item it sells at once.
struct ShopCardView: View {
    @ObservedObject var store: Store
    let shop: Shop
    var body: some View {
        let grid = shopGrid(shop: shop, items: store.state?.items ?? [])
        VStack(spacing: 8) {
            ForEach(0..<3, id: \.self) { y in
                HStack(spacing: 8) {
                    ForEach(0..<4, id: \.self) { x in
                        if let slot = grid[y][x] {
                            IconSlot(store: store, key: slot.item.keys, title: slot.item.name,
                                      subtitle: "Магазин: \(shop.name)\nRawcode юнита \(slot.unit.code); предметы: \(slot.item.codes.joined(separator: ", "))",
                                      icon: slot.unit.icon)
                        } else {
                            RoundedRectangle(cornerRadius: 4).fill(HUD.slot.opacity(0.6)).frame(width: 64, height: 64)
                                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.white.opacity(0.08)))
                                .frame(width: 78, height: 88, alignment: .top)
                        }
                    }
                }
            }
        }
        .padding(10).background(HUD.stone, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(HUD.gold.opacity(0.4)))
    }
}

struct ItemsView: View {
    @ObservedObject var store: Store
    @State private var selectedShop: String? = nil

    var shops: [Shop] { store.state?.shops ?? [] }

    var body: some View {
        HSplitView {
            List(selection: $selectedShop) {
                Section("Магазины") {
                    ForEach(shops) { shop in
                        VStack(alignment: .leading, spacing: 1) {
                            Text(shop.name)
                            Text("\(shop.code) · юнитов \(shop.units.count)").font(.caption2).foregroundStyle(.secondary)
                        }.tag(shop.code as String?)
                    }
                }
            }.frame(minWidth: 220, maxWidth: 300)

            Group {
                if let code = selectedShop, let shop = shops.first(where: { $0.code == code }) {
                    shopDetail(shop)
                } else if let shop = shops.first {
                    shopDetail(shop)
                } else {
                    Text("Нет магазинов").foregroundStyle(.secondary).frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .onChange(of: store.state?.generated) { _ in if selectedShop == nil { selectedShop = shops.first?.code } }
    }

    @ViewBuilder func shopDetail(_ shop: Shop) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .firstTextBaseline) {
                    Text(shop.name).font(.title.bold())
                    Text("[\(shop.code)]").foregroundStyle(.secondary)
                    Spacer()
                    Toggle("Герой рядом", isOn: Binding(get: { !store.showDisabled }, set: { store.showDisabled = !$0 }))
                        .toggleStyle(.switch).controlSize(.small)
                }
                ShopCardView(store: store, shop: shop)
                Text("Иконка ячейки берётся у юнита-товара; при замене та же картинка ставится и предметам в инвентаре.")
                    .font(.footnote).foregroundStyle(.secondary)
            }.padding()
        }
    }

}

// MARK: - Inventory (item families, both icon states side by side)

/// A drop-target pair for one variant (or the family's own shop icon): normal + disabled, side by side.
struct InventoryVariantPair: View {
    @ObservedObject var store: Store
    let label: String
    let key: String
    let icon: IconInfo
    var body: some View {
        VStack(spacing: 3) {
            Text(label).font(.caption2).lineLimit(1).frame(maxWidth: 160)
            HStack(spacing: 6) {
                IconSlot(store: store, key: key, title: label, subtitle: "Обычная иконка", icon: icon, size: 48, forceDisabled: false)
                IconSlot(store: store, key: key, title: label, subtitle: "Серая иконка (DISBTN)", icon: icon, size: 48, forceDisabled: true)
            }
        }
    }
}

struct InventoryFamilyRow: View {
    @ObservedObject var store: Store
    let item: Item

    var effectiveVariants: [ItemVariant] {
        if !item.variants.isEmpty { return item.variants }
        let icon = item.icon_item ?? item.icon
        return [ItemVariant(art: icon.art, names: item.names ?? [item.name], codes: item.codes, label: item.name, keys: item.keys, icon: icon)]
    }
    var showsShopPair: Bool {
        let variants = effectiveVariants
        return !variants.contains { $0.art == item.icon.art }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(item.name).font(.headline)
                Text("×\(item.count)").foregroundStyle(.secondary)
                if let shops = item.in_shops, !shops.isEmpty {
                    Text(shops.joined(separator: ", ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 14) {
                    ForEach(effectiveVariants) { variant in
                        InventoryVariantPair(store: store, label: variant.label, key: variant.keys, icon: variant.icon)
                    }
                    if showsShopPair {
                        InventoryVariantPair(store: store, label: "в магазине", key: item.keys, icon: item.icon)
                    }
                }
            }
        }
        .padding(10).background(HUD.panel, in: RoundedRectangle(cornerRadius: 10))
    }
}

struct InventoryView: View {
    @ObservedObject var store: Store
    @State private var search = ""

    var families: [Item] {
        let all = store.state?.items ?? []
        let filtered: [Item]
        if search.isEmpty {
            filtered = all
        } else {
            filtered = all.filter { item in
                item.name.localizedCaseInsensitiveContains(search)
                    || (item.names ?? []).contains { $0.localizedCaseInsensitiveContains(search) }
                    || item.codes.contains { $0.localizedCaseInsensitiveContains(search) }
            }
        }
        return filtered.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var body: some View {
        VStack(spacing: 0) {
            TextField("Поиск предмета, названия или rawcode", text: $search).textFieldStyle(.roundedBorder).padding(10)
            List {
                ForEach(families) { item in
                    InventoryFamilyRow(store: store, item: item)
                        .listRowSeparator(.hidden)
                }
            }
            Text("Каждая пара: цветная и серая версии одного и того же файла. Перетаскивание на любую из них заменяет обе.")
                .font(.footnote).foregroundStyle(.secondary).padding(8)
        }
    }
}

// MARK: - Main window

struct ContentView: View {
    @StateObject private var store = Store()
    @State private var tab = "heroes"
    @State private var selection: String?
    @State private var search = ""

    var heroes: [Hero] {
        let all = store.state?.heroes ?? []
        guard !search.isEmpty else { return all }
        return all.filter { $0.name.localizedCaseInsensitiveContains(search) || $0.code.localizedCaseInsensitiveContains(search) || ($0.txt_name ?? "").localizedCaseInsensitiveContains(search) }
    }
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Picker("", selection: $tab) { Text("Герои").tag("heroes"); Text("Предметы").tag("items"); Text("Инвентарь").tag("inventory") }.pickerStyle(.segmented).frame(width: 320)
                Spacer()
                Text(store.mapName).font(.caption).foregroundStyle(.secondary)
                Button { store.refresh() } label: { Image(systemName: "arrow.clockwise") }.disabled(store.busy)
            }.padding(10)
            Divider()
            if tab == "heroes" {
                HSplitView {
                    VStack(spacing: 0) {
                        TextField("Поиск героя", text: $search).textFieldStyle(.roundedBorder).padding(8)
                        List(selection: $selection) {
                            Section("Общие") {
                                Label("Общие иконки", systemImage: "square.grid.3x3").tag("__common__" as String?)
                            }
                            Section("Герои (\(heroes.filter { $0.group != "other" }.count))") { ForEach(heroes.filter { $0.group != "other" }) { h in heroRow(h) } }
                            let others = heroes.filter { $0.group == "other" }
                            if !others.isEmpty { Section("Прочие юниты с геройскими способностями (\(others.count))") { ForEach(others) { h in heroRow(h) } } }
                        }
                    }.frame(minWidth: 230, maxWidth: 300)
                    if selection == "__common__" {
                        CommonIconsView(store: store)
                    } else if let hero = heroes.first(where: { $0.code == selection }) ?? heroes.first {
                        HeroConsole(store: store, hero: hero).id(hero.code + (store.state?.generated ?? ""))
                    } else {
                        VStack { Image(systemName: "person.3").font(.largeTitle); Text(store.busy ? "Читаю карту…" : "Нет героев") }.frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            } else if tab == "items" {
                ItemsView(store: store)
            } else {
                InventoryView(store: store)
            }
            Divider()
            HStack {
                if store.busy { ProgressView().controlSize(.small) }
                Text(store.status).font(.footnote).foregroundStyle(.secondary).lineLimit(2).textSelection(.enabled)
                Spacer()
            }.padding(8).background(.quaternary)
        }
        .frame(minWidth: 1100, minHeight: 720)
        .onChange(of: store.state?.generated) { _ in if selection == nil { selection = heroes.first?.code } }
    }
    func heroRow(_ h: Hero) -> some View {
        HStack {
            if let url = store.previewURL(h.icon.normal), let img = NSImage(contentsOf: url) {
                Image(nsImage: img).resizable().interpolation(.none).frame(width: 22, height: 22).cornerRadius(3)
            } else { Image(systemName: "person.crop.square").frame(width: 22, height: 22) }
            Text(h.name)
            Spacer()
            if h.saved_scales != nil || h.icon.override != nil || h.abilities.contains(where: { $0.icon.override != nil }) {
                Circle().fill(.green).frame(width: 6, height: 6)
            }
        }.tag(h.code)
    }
}

@main struct HeroWorkshopUIApp: App {
    var body: some Scene { WindowGroup("Hero Workshop") { ContentView() } }
}
