import SwiftUI
import UniformTypeIdentifiers

struct Ability: Codable, Identifiable, Hashable {
    var base_ability: String
    var source: String
    var label: String?
    var id: String { base_ability + source }
}

struct RelatedModel: Codable, Identifiable, Hashable {
    var rawcode: String
    var label: String
    var model_scale: Double
    var model_scale_base: Double?
    var id: String { rawcode }
}

struct Hero: Codable, Identifiable, Hashable {
    var hero: String
    var unit_rawcode: String
    var primary_model_scale: Double?
    var alternative_model_scale: Double?
    var is_unit: Bool?
    var related_models: [RelatedModel]?
    var abilities: [Ability]
    var extra_abilities: [Ability]?
    var id: String { unit_rawcode }
    var allAbilities: [Ability] { abilities + (extra_abilities ?? []) }
    var relatedModels: [RelatedModel] { related_models ?? [] }
}
struct Item: Codable, Identifiable, Hashable {
    var item: String; var item_rawcode: String; var abilities: [Ability]
    var id: String { item_rawcode }
}

struct CatalogIcon: Identifiable, Hashable {
    let url: URL
    var id: URL { url }
    var title: String {
        let file = url.deletingPathExtension().lastPathComponent
        let pack = url.deletingLastPathComponent().lastPathComponent
        return pack.isEmpty ? file : "\(pack) / \(file)"
    }
}

@MainActor final class WorkshopStore: ObservableObject {
    @Published var heroes: [Hero] = []
    @Published var units: [Hero] = []
    @Published var items: [Item] = []
    @Published var catalogIcons: [CatalogIcon] = []
    @Published var selection = ""
    @Published var status = ""
    let root: URL
    let iconRoot: URL

    init() {
        root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let environment = ProcessInfo.processInfo.environment
        if let override = environment["HERO_WORKSHOP_ICON_ROOT"], !override.isEmpty {
            iconRoot = URL(fileURLWithPath: override)
        } else {
            var configured: String?
            for name in ["workshop.json", "workshop.local.json"] {
                let url = root.appendingPathComponent(name)
                if let data = try? Data(contentsOf: url),
                   let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let value = object["icon_root"] as? String { configured = value }
            }
            if let configured, configured.hasPrefix("/") {
                iconRoot = URL(fileURLWithPath: configured)
            } else {
                iconRoot = root.appendingPathComponent(configured ?? "assets/icons")
            }
        }
        reload()
    }
    var selected: Hero? { heroes.first { $0.id == selection } }
    func heroFolder(_ hero: Hero) -> URL {
        let section = hero.is_unit == true ? "units" : "heroes"
        return root.appendingPathComponent(section).appendingPathComponent("\(safe(hero.hero))__\(hero.unit_rawcode)")
    }
    func itemFolder(_ item: Item) -> URL { root.appendingPathComponent("items/\(safe(item.item))__\(item.item_rawcode)") }
    func heroAssetFolder(_ hero: Hero) -> URL {
        let section = hero.is_unit == true ? "units" : "heroes"
        return iconRoot.appendingPathComponent(section).appendingPathComponent("\(safe(hero.hero))__\(hero.unit_rawcode)")
    }
    func itemAssetFolder(_ item: Item) -> URL { iconRoot.appendingPathComponent("items/\(safe(item.item))__\(item.item_rawcode)") }
    func slotFolder(_ hero: Hero, _ index: Int, _ ability: Ability) -> URL {
        heroAssetFolder(hero).appendingPathComponent(String(format: "slots/%02d_%@", index + 1, ability.base_ability))
    }
    func safe(_ name: String) -> String {
        name.replacingOccurrences(of: "[^A-Za-z0-9_]", with: "_", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
    }
    func reload() {
        let directory = root.appendingPathComponent("heroes")
        let files = (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []
        heroes = files.compactMap { folder in
            let config = folder.appendingPathComponent("hero.json")
            guard let data = try? Data(contentsOf: config) else { return nil }
            return try? JSONDecoder().decode(Hero.self, from: data)
        }.sorted { $0.hero.localizedCaseInsensitiveCompare($1.hero) == .orderedAscending }
        if selection.isEmpty || !heroes.contains(where: { $0.id == selection }) { selection = heroes.first?.id ?? "" }
        let unitDirectory = root.appendingPathComponent("units")
        let unitFiles = (try? FileManager.default.contentsOfDirectory(at: unitDirectory, includingPropertiesForKeys: nil)) ?? []
        units = unitFiles.compactMap { folder in
            guard let data = try? Data(contentsOf: folder.appendingPathComponent("hero.json")) else { return nil }
            return try? JSONDecoder().decode(Hero.self, from: data)
        }.sorted { $0.hero.localizedCaseInsensitiveCompare($1.hero) == .orderedAscending }
        let itemDirectory = root.appendingPathComponent("items")
        let itemFiles = (try? FileManager.default.contentsOfDirectory(at: itemDirectory, includingPropertiesForKeys: nil)) ?? []
        items = itemFiles.compactMap { folder in try? JSONDecoder().decode(Item.self, from: Data(contentsOf: folder.appendingPathComponent("item.json"))) }.sorted { $0.item.localizedCaseInsensitiveCompare($1.item) == .orderedAscending }
        let catalog = iconRoot.appendingPathComponent("catalog")
        let files = FileManager.default.enumerator(at: catalog, includingPropertiesForKeys: [.isRegularFileKey])?.compactMap { $0 as? URL } ?? []
        catalogIcons = files
            .filter { $0.pathExtension.lowercased() == "png" }
            .map(CatalogIcon.init)
            .sorted { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
        status = "Героев: \(heroes.count) · юнитов: \(units.count)"
    }
    func save(_ hero: Hero) {
        if hero.is_unit == true, let i = units.firstIndex(where: { $0.id == hero.id }) { units[i] = hero }
        else if let i = heroes.firstIndex(where: { $0.id == hero.id }) { heroes[i] = hero }
        else { return }
        do {
            let data = try JSONEncoder.pretty.encode(hero)
            try data.write(to: heroFolder(hero).appendingPathComponent("hero.json"), options: .atomic)
            status = "Сохранено: \(hero.hero)"
        } catch { status = "Ошибка сохранения: \(error.localizedDescription)" }
    }
    func importAsset(from source: URL, folder: URL, kind: String) {
        let ext = source.pathExtension.lowercased()
        guard ["blp", "png"].contains(ext) else { status = "Нужен PNG или BLP"; return }
        let target = folder.appendingPathComponent("\(kind).\(ext)")
        do {
            try FileManager.default.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? FileManager.default.removeItem(at: folder.appendingPathComponent("\(kind).png"))
            try? FileManager.default.removeItem(at: folder.appendingPathComponent("\(kind).blp"))
            try? FileManager.default.removeItem(at: folder.appendingPathComponent("\(kind).preview.png"))
            try? FileManager.default.removeItem(at: target)
            try FileManager.default.copyItem(at: source, to: target)
            if ext == "blp" { createBLPPreview(source: target, at: folder.appendingPathComponent("\(kind).preview.png")) }
            status = "Импортирован: \(source.lastPathComponent)"
            objectWillChange.send()
        } catch { status = "Ошибка импорта: \(error.localizedDescription)" }
    }
    func createBLPPreview(source: URL, at preview: URL) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "blp_to_png.py", source.path, preview.path]
        process.currentDirectoryURL = root
        try? process.run()
        process.waitUntilExit()
    }
    func removeAsset(folder: URL, kind: String) { try? FileManager.default.removeItem(at: folder.appendingPathComponent("\(kind).png")); try? FileManager.default.removeItem(at: folder.appendingPathComponent("\(kind).blp")); try? FileManager.default.removeItem(at: folder.appendingPathComponent("\(kind).preview.png")); status = "Слот очищен"; objectWillChange.send() }
    func addTriggered(to hero: Hero, rawcode: String) {
        let code = rawcode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard code.count == 4 else { status = "Rawcode должен состоять из 4 символов"; return }
        guard !hero.allAbilities.contains(where: { $0.base_ability == code }) else { status = "Этот rawcode уже есть"; return }
        var updated = hero; updated.extra_abilities = (updated.extra_abilities ?? []) + [Ability(base_ability: code, source: "triggered")]
        save(updated)
        let folder = slotFolder(updated, updated.allAbilities.count - 1, updated.allAbilities.last!)
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        status = "Добавлена trigger-ability \(code)"
    }
    func addRelatedModel(to hero: Hero, rawcode: String, label: String) {
        let code = rawcode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard code.count == 4 else { status = "Rawcode модели должен состоять из 4 символов"; return }
        guard !hero.relatedModels.contains(where: { $0.rawcode == code }) else { status = "Эта связанная модель уже добавлена"; return }
        var updated = hero
        updated.related_models = updated.relatedModels + [RelatedModel(rawcode: code, label: label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Связанная модель" : label, model_scale: 1.0, model_scale_base: nil)]
        save(updated); reload()
    }
    func saveRelatedScale(hero: Hero, rawcode: String, scale: Double) {
        var updated = hero
        guard var related = updated.related_models, let index = related.firstIndex(where: { $0.rawcode == rawcode }) else { return }
        related[index].model_scale = scale
        updated.related_models = related
        save(updated)
    }
    func apply(_ hero: Hero) {
        let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "workshop.py", "apply", hero.unit_rawcode]
        process.currentDirectoryURL = root
        let pipe = Pipe(); process.standardOutput = pipe; process.standardError = pipe
        do { try process.run(); process.waitUntilExit()
            let text = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            status = process.terminationStatus == 0 ? "Применено: \(hero.hero)" : "Ошибка применения: \(text)"
        } catch { status = "Не удалось запустить конвейер: \(error.localizedDescription)" }
    }
    func applyItem(_ item: Item) {
        let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/env"); process.arguments = ["python3", "workshop.py", "apply-item", item.item_rawcode]; process.currentDirectoryURL = root
        let pipe = Pipe(); process.standardOutput = pipe; process.standardError = pipe
        do { try process.run(); process.waitUntilExit(); let text=String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self); status = process.terminationStatus == 0 ? "Применён предмет: \(item.item)" : "Ошибка применения: \(text)" } catch { status="Не удалось применить предмет: \(error.localizedDescription)" }
    }
}

extension JSONEncoder {
    static var pretty: JSONEncoder { let e = JSONEncoder(); e.outputFormatting = [.prettyPrinted, .sortedKeys]; return e }
}

struct BlpSlot: View {
    @ObservedObject var store: WorkshopStore
    let hero: Hero
    let index: Int
    let ability: Ability
    let kind: String
    var folder: URL { store.slotFolder(hero, index, ability) }
    var asset: URL? { [folder.appendingPathComponent(kind + ".png"), folder.appendingPathComponent(kind + ".blp")].first { FileManager.default.fileExists(atPath: $0.path) } }
    var preview: URL? { [folder.appendingPathComponent(kind + ".png"), folder.appendingPathComponent(kind + ".preview.png")].first { FileManager.default.fileExists(atPath: $0.path) } }
    @State private var importing = false
    var body: some View {
        HStack {
            Text(kind == "normal" ? "Активная" : "Неактивная").frame(width: 88, alignment: .leading)
            if let preview, let image = NSImage(contentsOf: preview) {
                Image(nsImage: image).resizable().interpolation(.none).scaledToFit().frame(width: 56, height: 56)
                    .background(.black, in: RoundedRectangle(cornerRadius: 5))
            } else {
                Image(systemName: "photo").frame(width: 56, height: 56).foregroundStyle(.secondary)
            }
            Text(asset?.lastPathComponent ?? "перетащите PNG или BLP сюда")
                .foregroundStyle(asset == nil ? .secondary : .primary)
                .lineLimit(1).frame(maxWidth: .infinity, alignment: .leading)
                .padding(7).background(.quaternary, in: RoundedRectangle(cornerRadius: 6))
                .onDrop(of: [.fileURL], isTargeted: nil) { providers in
                    providers.first?.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { value, _ in
                        if let data = value as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) { DispatchQueue.main.async { store.importAsset(from: url, folder: folder, kind: kind) } }
                    }; return true
                }
            Button("Выбрать") { importing = true }.fileImporter(isPresented: $importing, allowedContentTypes: [.png, UTType(filenameExtension: "blp")!]) { result in
                if case let .success(url) = result { store.importAsset(from: url, folder: folder, kind: kind) }
            }
            Button(role: .destructive) { store.removeAsset(folder: folder, kind: kind) } label: { Image(systemName: "trash") }.disabled(asset == nil)
        }
    }
}

struct HeroEditor: View {
    @ObservedObject var store: WorkshopStore
    let hero: Hero
    @State private var primaryScale: Double
    @State private var alternativeScale: Double
    @State private var triggered = ""
    @State private var relatedRawcode = ""
    @State private var relatedLabel = ""
    init(store: WorkshopStore, hero: Hero) {
        self.store = store
        self.hero = hero
        _primaryScale = State(initialValue: hero.primary_model_scale ?? 1.0)
        _alternativeScale = State(initialValue: hero.alternative_model_scale ?? 1.0)
    }
    func abilityTitle(_ ability: Ability, index: Int) -> String {
        ability.label ?? "Способность \(index + 1)"
    }
    func sourceTitle(_ source: String) -> String {
        switch source {
        case "heroAbilList": return "геройская"
        case "abilList": return "обычная"
        default: return "триггерная"
        }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack { Text(hero.hero).font(.title.bold()); Text("[\(hero.unit_rawcode)]").foregroundStyle(.secondary); Spacer()
                    Button("Применить в карту") { store.apply(hero) }.buttonStyle(.borderedProminent) }
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Основная модель")
                        TextField("1.0", value: $primaryScale, format: .number.precision(.fractionLength(2))).frame(width: 90)
                        Stepper("", value: $primaryScale, in: 0.20...3.00, step: 0.05).labelsHidden()
                    }
                    HStack {
                        Text("Альтернативная модель")
                        TextField("1.0", value: $alternativeScale, format: .number.precision(.fractionLength(2))).frame(width: 90)
                        Stepper("", value: $alternativeScale, in: 0.20...3.00, step: 0.05).labelsHidden()
                    }
                    HStack {
                        Text("Число — итоговый масштаб модели: 1.20 всегда записывает ровно 1.20.").foregroundStyle(.secondary)
                        Spacer()
                        Button("Сохранить масштабы") {
                            var h = hero
                            h.primary_model_scale = primaryScale
                            h.alternative_model_scale = alternativeScale
                            store.save(h)
                        }
                    }
                }
                Divider()
                GroupBox("Призванные существа и превращения") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Добавьте rawcode юнита для призыва, метаморфозы или иной связанной модели. Её итоговый масштаб хранится отдельно от героя.")
                            .font(.footnote).foregroundStyle(.secondary)
                        ForEach(hero.relatedModels) { related in
                            RelatedModelRow(store: store, hero: hero, related: related)
                        }
                        HStack {
                            TextField("Rawcode, например H000", text: $relatedRawcode).frame(width: 150)
                            TextField("Название, например Медведь", text: $relatedLabel)
                            Button("Добавить") { store.addRelatedModel(to: hero, rawcode: relatedRawcode, label: relatedLabel); relatedRawcode = ""; relatedLabel = "" }
                        }
                    }.padding(.vertical, 4)
                }
                Divider()
                GroupBox("Иконка героя") {
                    PortraitSlot(store: store, folder: store.heroAssetFolder(hero), kind: "portrait")
                    Text("Это кнопка/иконка героя, а не 3D-портрет модели.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                ForEach(Array(hero.allAbilities.enumerated()), id: \.element.id) { index, ability in
                    VStack(alignment: .leading, spacing: 7) {
                        Text("\(index + 1). \(abilityTitle(ability, index: index))").font(.headline)
                        Text("Rawcode: \(ability.base_ability) · \(sourceTitle(ability.source))")
                            .font(.footnote).foregroundStyle(.secondary)
                        BlpSlot(store: store, hero: hero, index: index, ability: ability, kind: "normal")
                        BlpSlot(store: store, hero: hero, index: index, ability: ability, kind: "disabled")
                    }.padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                }
                if hero.hero.lowercased().contains("invoker") {
                    GroupBox("Invoker: заклинание, выдаваемое триггером") {
                        HStack { TextField("Rawcode, например A123", text: $triggered); Button("Добавить слот") { store.addTriggered(to: hero, rawcode: triggered); triggered = "" } }
                    }
                }
            }.padding()
        }
    }
}

struct RelatedModelRow: View {
    @ObservedObject var store: WorkshopStore
    let hero: Hero
    let related: RelatedModel
    @State private var scale: Double
    init(store: WorkshopStore, hero: Hero, related: RelatedModel) {
        self.store = store; self.hero = hero; self.related = related
        _scale = State(initialValue: related.model_scale)
    }
    var body: some View {
        HStack {
            Text(related.label).frame(minWidth: 160, alignment: .leading)
            Text("[\(related.rawcode)]").foregroundStyle(.secondary)
            Spacer()
            TextField("1.0", value: $scale, format: .number.precision(.fractionLength(2))).frame(width: 80)
            Stepper("", value: $scale, in: 0.20...3.00, step: 0.05).labelsHidden()
            Button("Сохранить") { store.saveRelatedScale(hero: hero, rawcode: related.rawcode, scale: scale) }
        }
    }
}

struct ItemEditor: View {
    @ObservedObject var store: WorkshopStore
    @State private var selection = ""
    @State private var search = ""
    var filtered: [Item] { store.items.filter { search.isEmpty || $0.item.localizedCaseInsensitiveContains(search) || $0.item_rawcode.localizedCaseInsensitiveContains(search) } }
    var selected: Item? { store.items.first { $0.id == selection } }
    var body: some View {
        HSplitView {
            VStack { TextField("Поиск предмета или rawcode", text: $search).textFieldStyle(.roundedBorder).padding(8); List(selection: $selection) { ForEach(filtered) { Text($0.item).tag($0.id) } } }.frame(minWidth: 240)
            if let item=selected { ScrollView { VStack(alignment: .leading, spacing: 14) { HStack { Text(item.item).font(.title.bold()); Text("[\(item.item_rawcode)]").foregroundStyle(.secondary); Spacer(); Button("Применить в карту") { store.applyItem(item) }.buttonStyle(.borderedProminent) }
                ForEach(Array(item.abilities.enumerated()), id: \.element.id) { index, ability in
                    let folder=store.itemAssetFolder(item).appendingPathComponent(String(format:"slots/%02d_%@",index+1,ability.base_ability))
                    VStack(alignment:.leading) {
                        Text(ability.label ?? "Способность предмета \(index + 1)").font(.headline)
                        Text("Rawcode: \(ability.base_ability)").font(.footnote).foregroundStyle(.secondary)
                        ItemSlot(store:store, folder:folder, kind:"normal")
                        ItemSlot(store:store, folder:folder, kind:"disabled")
                    }.padding().background(.thinMaterial,in:RoundedRectangle(cornerRadius:10))
                }
            }.padding() } } else { Text("Выберите предмет").frame(maxWidth:.infinity,maxHeight:.infinity) }
        }.onAppear { selection=store.items.first?.id ?? "" }
    }
}

struct ItemSlot: View {
    @ObservedObject var store: WorkshopStore; let folder: URL; let kind: String; @State private var importing=false
    var asset: URL? { [folder.appendingPathComponent(kind+".png"),folder.appendingPathComponent(kind+".blp")].first { FileManager.default.fileExists(atPath:$0.path) } }
    var preview: URL? { [folder.appendingPathComponent(kind+".png"),folder.appendingPathComponent(kind+".preview.png")].first { FileManager.default.fileExists(atPath:$0.path) } }
    var body: some View { HStack { Text(kind == "normal" ? "Активная" : "Неактивная").frame(width:88,alignment:.leading); if let preview,let image=NSImage(contentsOf:preview) { Image(nsImage:image).resizable().interpolation(.none).scaledToFit().frame(width:56,height:56).background(.black,in:RoundedRectangle(cornerRadius:5)) } else { Image(systemName:"photo").frame(width:56,height:56).foregroundStyle(.secondary) }; Text(asset?.lastPathComponent ?? "Перетащите PNG или BLP сюда").foregroundStyle(asset == nil ? .secondary : .primary).frame(maxWidth:.infinity,alignment:.leading).padding(7).background(.quaternary,in:RoundedRectangle(cornerRadius:6)).onDrop(of:[.fileURL],isTargeted:nil){providers in providers.first?.loadItem(forTypeIdentifier:UTType.fileURL.identifier,options:nil){value,_ in if let data=value as? Data,let url=URL(dataRepresentation:data,relativeTo:nil){DispatchQueue.main.async{store.importAsset(from:url,folder:folder,kind:kind)}}};return true}; Button("Выбрать"){importing=true}.fileImporter(isPresented:$importing,allowedContentTypes:[.png,UTType(filenameExtension:"blp")!]){result in if case let .success(url)=result {store.importAsset(from:url,folder:folder,kind:kind)}}; Button(role:.destructive){store.removeAsset(folder:folder,kind:kind)}label:{Image(systemName:"trash")}.disabled(asset==nil) } }
}

struct PortraitSlot: View {
    @ObservedObject var store: WorkshopStore; let folder: URL; let kind: String; @State private var importing = false
    var asset: URL? { [folder.appendingPathComponent(kind+".png"),folder.appendingPathComponent(kind+".blp")].first { FileManager.default.fileExists(atPath:$0.path) } }
    var preview: URL? { [folder.appendingPathComponent(kind+".png"),folder.appendingPathComponent(kind+".preview.png")].first { FileManager.default.fileExists(atPath:$0.path) } }
    var body: some View { HStack { if let preview, let image=NSImage(contentsOf:preview) { Image(nsImage:image).resizable().interpolation(.none).scaledToFit().frame(width:64,height:64).background(.black,in:RoundedRectangle(cornerRadius:5)) } else { Image(systemName:"person.crop.square").frame(width:64,height:64).foregroundStyle(.secondary) }; Text(asset?.lastPathComponent ?? "Перетащите PNG или BLP сюда").foregroundStyle(asset == nil ? .secondary : .primary).frame(maxWidth:.infinity,alignment:.leading).padding(7).background(.quaternary,in:RoundedRectangle(cornerRadius:6)).onDrop(of:[.fileURL],isTargeted:nil){providers in providers.first?.loadItem(forTypeIdentifier:UTType.fileURL.identifier,options:nil){value,_ in if let data=value as? Data,let url=URL(dataRepresentation:data,relativeTo:nil){DispatchQueue.main.async{store.importAsset(from:url,folder:folder,kind:kind)}}};return true}; Button("Выбрать"){importing=true}.fileImporter(isPresented:$importing,allowedContentTypes:[.png,UTType(filenameExtension:"blp")!]){result in if case let .success(url)=result {store.importAsset(from:url,folder:folder,kind:kind)}}; Button(role:.destructive){store.removeAsset(folder:folder,kind:kind)}label:{Image(systemName:"trash")}.disabled(asset==nil) } }
}

struct ContentView: View {
    @StateObject private var store = WorkshopStore()
    @State private var tab = "heroes"
    @State private var unitSelection = ""
    var body: some View {
        VStack(spacing: 0) {
            Picker("Раздел", selection: $tab) { Text("Герои").tag("heroes"); Text("Юниты и крипы").tag("units"); Text("Предметы").tag("items"); Text("Каталог иконок").tag("catalog") }.pickerStyle(.segmented).padding()
            if tab == "heroes" {
                HSplitView {
                    List(selection: $store.selection) { ForEach(store.heroes) { Text($0.hero).tag($0.id) } }.frame(minWidth: 210)
                    if let hero = store.selected { HeroEditor(store: store, hero: hero) } else { VStack { Image(systemName: "person.3").font(.largeTitle); Text("Нет героев") }.frame(maxWidth: .infinity, maxHeight: .infinity) }
                }
            } else if tab == "units" {
                HSplitView {
                    List(selection: $unitSelection) { ForEach(store.units) { Text($0.hero).tag($0.id) } }.frame(minWidth: 210)
                    if let unit = store.units.first(where: { $0.id == unitSelection }) ?? store.units.first {
                        HeroEditor(store: store, hero: unit)
                    } else {
                        VStack { Image(systemName: "pawprint").font(.largeTitle); Text("Нет юнитов") }.frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }.onAppear { if unitSelection.isEmpty { unitSelection = store.units.first?.id ?? "" } }
            } else if tab == "items" { ItemEditor(store: store) }
            else { CatalogView(store: store) }
            Text(store.status).font(.footnote).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading).padding(8).background(.quaternary)
        }.frame(minWidth: 900, minHeight: 650)
    }
}

struct CatalogView: View {
    @ObservedObject var store: WorkshopStore
    private let columns = Array(repeating: GridItem(.flexible(minimum: 86), spacing: 10), count: 8)
    var body: some View {
        ScrollView {
            if store.catalogIcons.isEmpty {
                ContentUnavailableView("Каталог пуст", systemImage: "photo.on.rectangle", description: Text("Поместите PNG или BLP-наборы в assets/icons/catalog/."))
            } else {
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(store.catalogIcons) { icon in
                        VStack(spacing: 4) {
                            if let image = NSImage(contentsOf: icon.url) {
                                Image(nsImage: image).resizable().interpolation(.none).scaledToFit()
                                    .frame(width: 64, height: 64).background(.black, in: RoundedRectangle(cornerRadius: 5))
                            }
                            Text(icon.title).font(.caption2).lineLimit(2).multilineTextAlignment(.center)
                        }.help(icon.title)
                    }
                }.padding()
            }
        }
    }
}

@main struct HeroWorkshopUIApp: App { var body: some Scene { WindowGroup { ContentView() } } }
