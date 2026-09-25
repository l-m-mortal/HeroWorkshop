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
struct Ability: Codable, Hashable, Identifiable {
    var code: String
    var name: String
    var hero: Bool
    var buttonpos: [Int]?
    var researchpos: [Int]?
    var icon: IconInfo
    var id: String { code }
    var visible: Bool { icon.art != nil || buttonpos != nil }
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
    var id: String { code }
}
struct Hero: Codable, Hashable, Identifiable {
    var code: String
    var name: String
    var txt_name: String?
    var model: String?
    var scale: Double?
    var p3_scale: Double?
    var morph: String?
    var morph_scale: Double?
    var alt: String?
    var alt_scale: Double?
    var saved_scales: SavedScales?
    var icon: IconInfo
    var abilities: [Ability]
    var related: [RelatedUnit]?
    var group: String?              // hero | other
    var id: String { code }
}
struct Item: Codable, Hashable, Identifiable {
    var code: String?
    var name: String
    var codes: [String]
    var keys: String                // "item:A,item:B" — every rawcode of this item that has an icon
    var count: Int
    var distinct_arts: Int
    var icon: IconInfo
    var id: String { name }
}
struct MapState: Codable {
    var map: String
    var game_root: String
    var generated: String
    var work_dir: String
    var heroes: [Hero]
    var items: [Item]
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
    @State private var targeted = false
    @State private var importing = false

    var resolved: Resolved { store.showDisabled ? icon.disabled : icon.normal }
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
            .contextMenu {
                Button("Выбрать файл…") { importing = true }
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
            Text(title).font(.system(size: 10)).lineLimit(1).frame(width: size + 14)
            Text(originText).font(.system(size: 8)).foregroundStyle(icon.override != nil ? Color.green : Color.secondary).lineLimit(1)
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
                            IconSlot(store: store, key: "ability:\(a.code)", title: a.name, subtitle: "Способность \(a.code)" + (a.hero ? " (геройская)" : ""), icon: a.icon)
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
                    HStack {
                        Text("Масштаб").font(.callout)
                        TextField("1.0", value: $scale, format: .number.precision(.fractionLength(2))).frame(width: 64)
                        Stepper("", value: $scale, in: 0.1...5.0, step: 0.05).labelsHidden()
                        Button("Применить") { store.setScale(code: unit.code, scale: scale) }.controlSize(.small).disabled(store.busy)
                    }
                    Text("в карте \(unit.scale.map { $0.formatted() } ?? "—")" + (unit.p3_scale.map { " · P3 \($0.formatted())" } ?? "")).font(.caption2).foregroundStyle(.secondary)
                    if let m = unit.model { Text(m).font(.caption2).foregroundStyle(.secondary).lineLimit(1).textSelection(.enabled) }
                }
                if unit.abilities.contains(where: { $0.visible }) { CommandCard(store: store, abilities: unit.abilities) }
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
    @State private var morph: Double
    @State private var alt: Double
    @State private var relatedCode = ""

    init(store: Store, hero: Hero) {
        self.store = store; self.hero = hero
        _scale = State(initialValue: hero.saved_scales?.scale ?? hero.scale ?? 1.0)
        _morph = State(initialValue: hero.saved_scales?.morph ?? hero.morph_scale ?? hero.scale ?? 1.0)
        _alt = State(initialValue: hero.saved_scales?.alt ?? hero.alt_scale ?? 1.0)
    }

    var grid: [[Ability?]] { commandGrid(hero.abilities) }
    var overflow: [Ability] { gridOverflow(hero.abilities) }
    var hidden: [Ability] { hero.abilities.filter { !$0.visible } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .firstTextBaseline) {
                    Text(hero.name).font(.title.bold())
                    Text("[\(hero.code)]").foregroundStyle(.secondary)
                    if let t = hero.txt_name, t != hero.name { Text("· \(t)").foregroundStyle(.secondary) }
                    Spacer()
                    Toggle("Серые (DISBTN)", isOn: $store.showDisabled).toggleStyle(.switch).controlSize(.small)
                }
                if let model = hero.model { Text("Модель: \(model)").font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }

                // The in-game bottom console: portrait | info + scales | command card
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
                        ForEach(overflow) { a in IconSlot(store: store, key: "ability:\(a.code)", title: a.name, subtitle: "Способность \(a.code)", icon: a.icon) }
                    }
                }
                Text("Связанные юниты: морф-форма, альтернативная модель, призывы").font(.headline)
                ForEach(hero.related ?? []) { unit in RelatedUnitCard(store: store, hero: hero, unit: unit) }
                HStack {
                    TextField("Rawcode юнита, например n0EE", text: $relatedCode).frame(width: 220)
                    Button("Добавить связанный юнит") {
                        store.addRelated(hero: hero.code, unit: relatedCode.trimmingCharacters(in: .whitespaces)); relatedCode = ""
                    }.disabled(relatedCode.trimmingCharacters(in: .whitespaces).count != 4 || store.busy)
                    Text("Для призывов, которые создаются триггером и не видны в данных способности.").font(.caption2).foregroundStyle(.secondary)
                }
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
            if let m = hero.morph { scaleRow("Морф \(m)", value: $morph, current: hero.morph_scale, extra: nil) }
            if let a = hero.alt { scaleRow("Альтернатива \(a)", value: $alt, current: hero.alt_scale, extra: nil) }
            HStack {
                Button("Применить масштаб") {
                    store.setScale(hero: hero, scale: scale, morph: hero.morph != nil ? morph : nil, alt: hero.alt != nil ? alt : nil)
                }.buttonStyle(.borderedProminent).disabled(store.busy)
                if let saved = hero.saved_scales?.applied { Text("сохранено \(saved)").font(.caption2).foregroundStyle(.secondary) }
            }
            Text("Значение абсолютное: 1.20 записывает ровно 1.20 в unitUI и в таблицу P3, поэтому масштаб переживает смерть героя.")
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

// MARK: - Items

struct ItemsView: View {
    @ObservedObject var store: Store
    @State private var search = ""
    var items: [Item] {
        let all = store.state?.items ?? []
        guard !search.isEmpty else { return all }
        return all.filter { $0.name.localizedCaseInsensitiveContains(search) || $0.codes.contains { $0.localizedCaseInsensitiveContains(search) } }
    }
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                TextField("Поиск предмета или rawcode", text: $search).textFieldStyle(.roundedBorder)
                Toggle("Серые (DISBTN)", isOn: $store.showDisabled).toggleStyle(.switch).controlSize(.small)
            }.padding(10)
            ScrollView {
                LazyVGrid(columns: Array(repeating: GridItem(.fixed(84), spacing: 6), count: 10), spacing: 10) {
                    ForEach(items) { item in
                        IconSlot(store: store, key: item.keys, title: item.count > 1 ? "\(item.name) ×\(item.count)" : item.name,
                                 subtitle: "Rawcode: \(item.codes.joined(separator: ", "))" + (item.distinct_arts > 1 ? "\nРазных иконок сейчас: \(item.distinct_arts)" : ""), icon: item.icon)
                    }
                }.padding(10).background(HUD.panel, in: RoundedRectangle(cornerRadius: 12)).padding()
            }
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
                Picker("", selection: $tab) { Text("Герои").tag("heroes"); Text("Предметы").tag("items") }.pickerStyle(.segmented).frame(width: 220)
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
                            Section("Герои (\(heroes.filter { $0.group != "other" }.count))") { ForEach(heroes.filter { $0.group != "other" }) { h in heroRow(h) } }
                            let others = heroes.filter { $0.group == "other" }
                            if !others.isEmpty { Section("Прочие юниты с геройскими способностями (\(others.count))") { ForEach(others) { h in heroRow(h) } } }
                        }
                    }.frame(minWidth: 230, maxWidth: 300)
                    if let hero = heroes.first(where: { $0.code == selection }) ?? heroes.first {
                        HeroConsole(store: store, hero: hero).id(hero.code + (store.state?.generated ?? ""))
                    } else {
                        VStack { Image(systemName: "person.3").font(.largeTitle); Text(store.busy ? "Читаю карту…" : "Нет героев") }.frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            } else {
                ItemsView(store: store)
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
