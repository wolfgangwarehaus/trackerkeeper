// tracker keeper — the phone interface (trackerkeeper/quick/__init__.py).
// Context properties: `fleet` (quick/fleet_model.py Fleet), `theme` (Theme).
//
//   tracker keeper  3 new        ⟳
//   (All) (New 3) (Gaming) (iPhone) (PC)
//   GAMING · 2 new
//   ● Slay the Spire 2              5h
//     v0.110.0 · Steam
//   …                                 (+)
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

    Shortcut {
        sequences: [StandardKey.Back, "Esc", "Back"]
        onActivated: win.back()
    }

    DetailSheet {
        id: detail
        onEdit: name => win.openEdit(name)
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

            header: Column {
                width: parent ? parent.width : 400
                Item {  // title bar
                    width: parent.width
                    height: 56
                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 20
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "tracker keeper"
                            color: theme.text
                            font.pixelSize: 21
                            font.weight: Font.DemiBold
                        }
                        Rectangle {  // "3 new" pill — the one number that matters
                            objectName: "newPill"
                            anchors.verticalCenter: parent.verticalCenter
                            visible: fleet.updateCount > 0
                            width: pill.implicitWidth + 16
                            height: 24
                            radius: 12
                            color: theme.accentWash
                            Label {
                                id: pill
                                anchors.centerIn: parent
                                text: qsTr("%1 to update").arg(fleet.updateCount)
                                color: theme.accent
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                    IconButton {
                        objectName: "refreshButton"
                        anchors.right: parent.right
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        iconName: "refresh"
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
                }
                ListView {  // filter chips: All · New · each category
                    objectName: "chips"
                    width: parent.width
                    height: 48
                    orientation: ListView.Horizontal
                    spacing: 8
                    leftMargin: 16
                    rightMargin: 16
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    model: [{ key: "all", label: qsTr("All") }, { key: "new", label: qsTr("Updates") }]
                           .concat(fleet.groups.map(g => ({ key: g, label: g })))
                    delegate: Chip {
                        required property var modelData
                        objectName: "chip_" + modelData.key
                        anchors.verticalCenter: parent ? parent.verticalCenter : undefined
                        text: modelData.label
                        // `+ 0 * updateCount`: a slot call has no notify signal,
                        // so lean on one that changes whenever the counts can.
                        count: modelData.key === "all" ? 0
                               : modelData.key === "new" ? fleet.updateCount
                               : fleet.sectionNews(modelData.key) + 0 * fleet.updateCount
                        selected: fleet.filter === modelData.key
                        onClicked: fleet.filter = modelData.key
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
                readonly property bool pulledFar: contentY - originY < -80
                onDragEnded: if (pulledFar && !fleet.checking) fleet.refresh()

                header: Item {
                    width: list.width
                    height: 30
                    Label {
                        anchors.centerIn: parent
                        text: fleet.checking ? qsTr("checking…")
                              : list.pulledFar ? qsTr("release to check")
                              : (fleet.status || qsTr("pull down to check"))
                        color: theme.textFaint
                        font.pixelSize: 12
                    }
                }

                section.property: "section"
                section.criteria: ViewSection.FullString
                section.delegate: Item {
                    required property string section
                    width: list.width
                    height: 40
                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 20
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 6
                        spacing: 8
                        Label {
                            text: section.toUpperCase()
                            color: theme.textDim
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            font.letterSpacing: 1.2
                        }
                        Label {
                            readonly property int n: fleet.sectionNews(section) + 0 * fleet.updateCount
                            visible: n > 0
                            text: qsTr("%1 to update").arg(n)
                            color: theme.accent
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                    }
                }

                delegate: ItemRow {
                    onOpened: detail.show(name)
                    onMarkUpdated: fleet.markUpdated(name)
                }

                footer: Item { width: list.width; height: 96 }   // room under the + button

                Column {  // empty state
                    anchors.centerIn: parent
                    width: parent.width - 64
                    spacing: 16
                    visible: list.count === 0
                    Label {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: fleet.total === 0 ? qsTr("Track your first thing")
                              : qsTr("Nothing here")
                        color: theme.text
                        font.pixelSize: 18
                        font.weight: Font.DemiBold
                    }
                    Label {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        text: fleet.total === 0
                              ? qsTr("Apps, games, firmware — anything with a version. Tap + to add one.")
                              : qsTr("Everything in this view is up to date.")
                        color: theme.textDim
                        font.pixelSize: 14
                    }
                }
            }

            RoundButton {  // add
                objectName: "addButton"
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 20
                width: 60
                height: 60
                focusPolicy: Qt.NoFocus
                onClicked: win.openEdit("")
                background: Rectangle {
                    radius: width / 2
                    color: theme.accent
                    opacity: parent.pressed ? 0.8 : 1
                }
                contentItem: Item {
                    Icon { anchors.centerIn: parent; name: "plus"; tint: theme.onAccent; size: 28 }
                }
            }
        }
    }
}
