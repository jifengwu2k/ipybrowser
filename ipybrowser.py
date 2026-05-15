import sys

# Load pyexpat early so the conda libexpat is resolved before QtWebEngine
# pulls in the system libexpat
import xml.parsers.expat  # noqa: F401

import lxml.html
from PyQt6.QtCore import QUrl, QObject, pyqtSlot, pyqtSignal
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit
)
from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget


# --------------- Message Bridge: JS <-> PyQt slot -----------------
class ElementPickerBridge(QObject):
    elementPicked = pyqtSignal(str)  # HTML string of the picked element

    @pyqtSlot(str)
    def onElementPicked(self, html):
        self.elementPicked.emit(html)  # Forward as Qt signal


# --------------- Main Window -----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPyBrowser")

        # --- Nav Controls ---
        nav_layout = QHBoxLayout()
        self.back_btn = QPushButton('Back')
        self.forward_btn = QPushButton('Forward')
        self.refresh_btn = QPushButton('Refresh')
        self.pick_btn = QPushButton('Select Element')
        self.address_bar = QLineEdit()
        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self.forward_btn)
        nav_layout.addWidget(self.refresh_btn)
        nav_layout.addWidget(self.pick_btn)
        nav_layout.addWidget(self.address_bar)

        # --- Web View ---
        self.web_view = QWebEngineView()
        self.address_bar.setText("https://www.python.org/")
        self.web_view.setUrl(QUrl(self.address_bar.text()))

        # --- IPython Console ---
        self.ipython_console = self._create_ipython_console()

        # --- Message console ---
        self.message_console = QTextEdit()
        self.message_console.setReadOnly(True)
        self.message_console.setMaximumHeight(120)

        # --- Layout ---
        main_widget = QWidget()
        vlayout = QVBoxLayout(main_widget)
        vlayout.addLayout(nav_layout)
        vlayout.addWidget(self.web_view, stretch=2)
        vlayout.addWidget(self.ipython_console, stretch=1)
        vlayout.addWidget(self.message_console, stretch=0)
        self.setCentralWidget(main_widget)

        # --- Connections ---
        self.back_btn.clicked.connect(self.web_view.back)
        self.forward_btn.clicked.connect(self.web_view.forward)
        self.refresh_btn.clicked.connect(self.web_view.reload)
        self.address_bar.returnPressed.connect(self.load_url_from_bar)
        self.web_view.urlChanged.connect(self.on_new_url)
        self.web_view.loadFinished.connect(self.handle_load_finished)
        self.pick_btn.clicked.connect(self.activate_element_picker)

        # --- JS-Python bridge
        self.element_picker_bridge = ElementPickerBridge()
        self.element_picker_bridge.elementPicked.connect(self.on_element_html_captured)

        # WebChannel for JS/Python bridge
        self.web_channel = QWebChannel()
        self.web_channel.registerObject("pyPickerBridge", self.element_picker_bridge)
        self.web_view.page().setWebChannel(self.web_channel)

        # Make web_view accessible in IPython
        self.ipy_namespace['self'] = self.web_view
        self.write_message("In the IPython console, 'self' = QWebEngineView (the browser web view).")

        # For tempN tracking
        self.temp_counter = 0
        self.temp_names = []

    def load_url_from_bar(self):
        url_text = self.address_bar.text()
        self.web_view.setUrl(QUrl(url_text))

    def update_address_bar(self, url):
        self.address_bar.setText(url.toString())

    def on_new_url(self, url):
        self.update_address_bar(url)
        self._clear_html_and_tempvars()
        # We'll assign html only after load finished (see handle_load_finished)

    def handle_load_finished(self, ok):
        if ok:
            # Set 'html' in the namespace as lxml.html object
            def _set_html(page_html):
                try:
                    elem = lxml.html.fromstring(page_html)
                    ns = self.ipy_namespace
                    ns['html'] = elem
                    self.write_message(f"Page HTML element tree assigned as 'html' for {self.web_view.url().toString()} in the console.")
                except Exception as e:
                    self.write_message(f"<b>Could not parse HTML:</b> {e}")

            self.web_view.page().toHtml(_set_html)
        else:
            self.write_message("Page failed to load.")

    def _clear_html_and_tempvars(self):
        ns = self.ipy_namespace
        # Clear 'html' and all temp* variables
        for name in ['html'] + self.temp_names:
            if name in ns:
                try:
                    del ns[name]
                except Exception:
                    pass
        self.temp_counter = 0
        self.temp_names = []

    def _create_ipython_console(self):
        kernel_manager = QtInProcessKernelManager()
        kernel_manager.start_kernel()
        kernel = kernel_manager.kernel
        kernel.gui = 'qt'
        kernel.shell.banner1 = "Qt IPython Console (self = QWebEngineView)\n"
        self.kernel_client = kernel_manager.client()
        self.kernel_client.start_channels()

        self.ipy_namespace = kernel.shell.user_ns
        self.kernel_shell = kernel.shell
        self.ipy_namespace['lxml'] = lxml
        self.ipy_namespace['etree'] = lxml.etree

        console = RichJupyterWidget()
        console.set_default_style('linux')
        console.kernel_manager = kernel_manager
        console.kernel_client = self.kernel_client
        return console

    # ------------------ Messaging utility -------------------
    def write_message(self, txt):
        self.message_console.append(txt)

    # ------------------ Element Picker ----------------------
    def activate_element_picker(self):
        # Load qwebchannel.js if not loaded (once per page)
        js_code = """
        (function() {
            function startPicker() {
                const styleID = '__pyqt_highlight_style';
                if (!document.getElementById(styleID)) {
                    const style = document.createElement('style');
                    style.id = styleID;
                    style.innerHTML = '.\\__pyqt_highlight { outline: 2px solid red !important; cursor: pointer !important; }';
                    document.head.appendChild(style);
                }
                function clear() {
                    document.removeEventListener('mouseover', hoverHandler, true);
                    document.removeEventListener('mouseout', outHandler, true);
                    document.removeEventListener('click', clickHandler, true);
                    document.querySelectorAll('.__pyqt_highlight').forEach(el => el.classList.remove('__pyqt_highlight'));
                    const s = document.getElementById(styleID);
                    if (s) s.remove();
                }
                function hoverHandler(e) { e.target.classList.add('__pyqt_highlight'); }
                function outHandler(e) { e.target.classList.remove('__pyqt_highlight'); }
                function clickHandler(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    clear();
                    let html = e.target.outerHTML;
                    if (window.pyPickerBridge && window.pyPickerBridge.onElementPicked)
                        window.pyPickerBridge.onElementPicked(html);
                }
                document.addEventListener('mouseover', hoverHandler, true);
                document.addEventListener('mouseout', outHandler, true);
                document.addEventListener('click', clickHandler, true);
            }
            // If QWebChannel not in window, load it:
            if (typeof QWebChannel === 'undefined') {
                var s = document.createElement('script');
                s.src = 'qrc:///qtwebchannel/qwebchannel.js';
                s.onload = function() {
                    new QWebChannel(qt.webChannelTransport, function(channel) {
                        window.pyPickerBridge = channel.objects.pyPickerBridge;
                        startPicker();
                    });
                };
                document.head.appendChild(s);
            } else if (!window.pyPickerBridge) {
                new QWebChannel(qt.webChannelTransport, function(channel) {
                    window.pyPickerBridge = channel.objects.pyPickerBridge;
                    startPicker();
                });
            } else {
                startPicker();
            }
        })()
        """
        self.web_view.page().runJavaScript(js_code)
        self.write_message("Select an element in the browser window...")

    def on_element_html_captured(self, html):
        # Assign element to tempN only (raw HTML recoverable via lxml.html.tostring)
        n = self.temp_counter
        ns = self.ipy_namespace
        try:
            elem = lxml.html.fromstring(html)
            name_elem = f"temp{n}"
            ns[name_elem] = elem
            self.temp_names.append(name_elem)
            self.temp_counter += 1
            self.write_message(f"Element assigned as '{name_elem}' (see IPython console).")
        except Exception as e:
            self.write_message(f"<b>lxml error:</b> {e}")

    def closeEvent(self, event):
        self.kernel_client.stop_channels()
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
