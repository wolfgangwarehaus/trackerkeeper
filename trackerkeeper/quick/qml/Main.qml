// tracker keeper — the phone interface (trackerkeeper/quick/__init__.py).
// Context properties: `fleet` (quick/fleet_model.py Fleet), `theme` (Theme).
//
//   tracker keeper                       ⟳  ⋮
//   2 new updates  ·  All · checked 4:20
//
//   GAMING
//   ● GameNative                        1w
//     1.2.9 → 1.3.0 · Android
//
// Colour means news and nothing else: the header's "N new updates" and a
// row's dot + version are the only green on the list. The view filter and
// "track something new" live in the ⋮ sheet; pull down to check.
import QtQuick
import QtQuick.Controls

ApplicationWindow {
    id: win
    width: 402
    height: 820
    visible: true
    title: "tracker keeper"
    color: theme.background
    palette.buttonText: theme.text
    palette.windowText: theme.text
    palette.text: theme.text
    palette.window: theme.surface
    palette.base: theme.surface
    palette.highlight: theme.accent
    palette.highlightedText: theme.onAccent

    // Back: an open sheet first, then the page stack. (Back key / Esc / button.)
    function back() {
        if (detail.opened) {
            detail.close()
            return true
        }
        if (menu.opened) {
            menu.close()
            return true
        }
        if (stack.depth > 1) {
            stack.pop()
            return true
        }
        return false
    }
    function showDetail(name) {
        detail.show(name)
    }
    function openEdit(name) {
        stack.push(editPage, { original: name || "" })
    }
    function openMenu() {
        menu.open()
    }

    Shortcut {
        sequences: [StandardKey.Back, "Esc", "Back"]
        onActivated: win.back()
    }

    DetailSheet {
        id: detail
        onEdit: name => win.openEdit(name)
    }

    // ⋮ — what to show, and adding something new.
    Sheet {
        id: menu
        objectName: "menuSheet"

        SheetHeading { text: qsTr("SHOW") }
        Repeater {
            model: fleet.filterOptions
            SheetRow {
                required property var modelData
                objectName: "filter_" + modelData.key
                text: modelData.label
                current: fleet.filter === modelData.key
                count: modelData.count
                onClicked: {
                    fleet.filter = modelData.key
                    menu.close()
                }
            }
        }
        Rectangle { width: parent.width; height: 1; color: theme.divider }
        SheetRow {
            objectName: "addItem"
            iconName: "plus"
            text: qsTr("Track something new")
            onClicked: {
                menu.close()
                win.openEdit("")
            }
        }
    }

    Component {
        id: editPage
        EditPage { onDone: stack.pop() }
    }

    StackView {
        id: stack
        objectName: "stack"
        anchors.fill: parent
        initialItem: listPage
    }

    Component {
        id: listPage
        Page {
            objectName: "listPage"
            background: Rectangle { color: theme.background }

            header: Item {
                width: parent ? parent.width : 400
                height: 72
                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: 16
                    anchors.right: actions.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Label {
                        text: "tracker keeper"
                        color: theme.text
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                    }
                    Label {  // the news (green) · which view, when we last looked (quiet)
                        objectName: "subtitle"
                        width: parent.width
                        elide: Text.ElideRight
                        textFormat: Text.StyledText
                        font.pixelSize: 13
                        text: (fleet.newsLine
                               ? "<font color='" + theme.accent + "'>" + fleet.newsLine + "</font>"
                                 + "<font color='" + theme.textFaint + "'>  ·  </font>"
                               : "")
                              + "<font color='" + theme.textDim + "'>" + fleet.subtitle + "</font>"
                    }
                }
                Row {
                    id: actions
                    anchors.right: parent.right
                    anchors.rightMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    IconButton {
                        objectName: "refreshButton"
                        iconName: "refresh"
                        iconSize: 22
                        enabled: !fleet.checking
                        onClicked: fleet.refresh()
                        RotationAnimation on rotation {
                            running: fleet.checking
                            loops: Animation.Infinite
                            from: 0
                            to: 360
                            duration: 900
                            onStopped: parent.rotation = 0
                        }
                    }
                    IconButton {
                        objectName: "menuButton"
                        iconName: "more"
                        iconSize: 22
                        onClicked: menu.open()
                    }
                }
            }

            ListView {
                id: list
                objectName: "fleetList"
                anchors.fill: parent
                clip: true
                model: fleet.model
                boundsBehavior: Flickable.DragOverBounds
                // Pull down past the top and let go → check now.
                readonly property real pull: Math.max(0, originY - contentY)
                readonly property bool pulledFar: pull > 72
                onDragEnded: if (pulledFar && !fleet.checking) fleet.refresh()

                Label {  // sits in the gap a pull opens above the first row
                    y: -list.pull + (list.pull - height) / 2 - list.contentY + list.originY
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: list.pull > 12
                    opacity: Math.min(1, list.pull / 72)
                    text: list.pulledFar ? qsTr("Release to check") : qsTr("Pull to check")
                    color: theme.textDim
                    font.pixelSize: 13
                }

                section.property: "section"
                section.criteria: ViewSection.FullString
                section.delegate: Item {
                    required property string section
                    width: list.width
                    height: 44
                    Label {
                        anchors.left: parent.left
                        anchors.leftMargin: 16
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 6
                        text: section.toUpperCase()
                        color: theme.textFaint
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.2
                    }
                }

                delegate: ItemRow {
                    onOpened: detail.show(name)
                    onMarkUpdated: fleet.markUpdated(name)
                }

                footer: Item { width: list.width; height: 24 }

                Column {  // empty state
                    anchors.centerIn: parent
                    width: parent.width - 64
                    spacing: 12
                    visible: list.count === 0
                    Label {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: fleet.total === 0 ? qsTr("Track your first thing")
                              : qsTr("Nothing waiting")
                        color: theme.text
                        font.pixelSize: 18
                        font.weight: Font.DemiBold
                    }
                    Label {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        text: fleet.total === 0
                              ? qsTr("Apps, games, firmware — anything with a version.")
                              : qsTr("Everything in this view is up to date.")
                        color: theme.textDim
                        font.pixelSize: 14
                    }
                    PillButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: fleet.total === 0
                        iconName: "plus"
                        text: qsTr("Track something")
                        onClicked: win.openEdit("")
                    }
                }
            }
        }
    }
}
