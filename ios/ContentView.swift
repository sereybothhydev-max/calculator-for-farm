// Calculator for Farm — iPhone app shell.
// Replace everything in your project's ContentView.swift with this file.
// It shows the app (the "web" folder) full screen, works offline, and keeps
// your saved numbers on the phone between launches.

import SwiftUI
import WebKit
import UniformTypeIdentifiers

struct ContentView: View {
    var body: some View {
        FarmWebView()
            .ignoresSafeArea()          // the page handles the notch and home bar itself
    }
}

struct FarmWebView: UIViewRepresentable {
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        // Serve the app from inside the app bundle at farmapp://localhost/…
        // A fixed address like this keeps saved data (localStorage) safe between launches.
        config.setURLSchemeHandler(BundleFileHandler(), forURLScheme: "farmapp")
        config.websiteDataStore = .default()
        config.allowsInlineMediaPlayback = true

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = .systemBackground
        webView.scrollView.backgroundColor = .systemBackground
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.allowsBackForwardNavigationGestures = false
        webView.load(URLRequest(url: URL(string: "farmapp://localhost/index.html")!))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

/// Hands the files in the "web" folder to the web view.
final class BundleFileHandler: NSObject, WKURLSchemeHandler {
    func webView(_ webView: WKWebView, start urlSchemeTask: WKURLSchemeTask) {
        guard let url = urlSchemeTask.request.url else { return }
        var name = url.path
        if name.isEmpty || name == "/" { name = "/index.html" }
        name.removeFirst()   // drop the leading "/"

        // Works whether the folder was added as a blue folder ("web/…") or as loose files.
        let candidates = [
            Bundle.main.resourceURL?.appendingPathComponent("web").appendingPathComponent(name),
            Bundle.main.resourceURL?.appendingPathComponent(name)
        ].compactMap { $0 }

        guard let fileURL = candidates.first(where: { FileManager.default.fileExists(atPath: $0.path) }),
              let data = try? Data(contentsOf: fileURL) else {
            urlSchemeTask.didFailWithError(URLError(.fileDoesNotExist))
            return
        }

        let ext = fileURL.pathExtension.lowercased()
        let mime: String
        switch ext {
        case "html": mime = "text/html; charset=utf-8"
        case "webmanifest": mime = "application/manifest+json"
        default: mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
        }
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": mime,
                                                      "Content-Length": String(data.count),
                                                      "Cache-Control": "no-cache"])!
        urlSchemeTask.didReceive(response)
        urlSchemeTask.didReceive(data)
        urlSchemeTask.didFinish()
    }

    func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) {}
}

#Preview {
    ContentView()
}
