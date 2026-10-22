// Add or edit a tracked item — the phone's version of the desktop Add/Edit
// dialog, with the same fields and the same validation (Fleet.save).
import QtQuick
import QtQuick.Controls

Page {
    id: page
    objectName: "editPage"
    property string original: ""          // "" = adding
    property var item: original ? fleet.item(original) : ({})
    property string kind: item.kind || "github"
    readonly property var sourceList: fleet.sources()
    readonly property var source: sourceList.find(s => s.kind === kind) || ({})

    signal done()

    background: Rectangle { color: theme.background }

    function save() {
        var problem = fleet.save(original, {
            name: nameField.text, group: groupField.text, platform: platformField.text,
            kind: kind, ref: refField.text, installed: installedField.text,
            changelogUrl: changelogField.text
        })
        if (problem)
            error.text = problem
        else
            page.done()
    }

    header: Item {
        height: 56
        IconButton {
            anchors.left: parent.left
            anchors.leftMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            iconName: "back"
            onClicked: page.done()
        }
        Label {
            anchors.left: parent.left
            anchors.leftMargin: 60
            anchors.verticalCenter: parent.verticalCenter
            text: page.original ? qsTr("Edit") : qsTr("Track something")
            color: theme.text
            font.pixelSize: 19
            font.weight: Font.DemiBold
        }
        Button {
            objectName: "saveButton"
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            focusPolicy: Qt.NoFocus
            text: qsTr("Save")
            onClicked: page.save()
            contentItem: Label {   // high-contrast neutral: green means news
                text: parent.text
                color: theme.background
                font.pixelSize: 15
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                implicitWidth: 80
                implicitHeight: 40
                radius: 20
                color: theme.text
                opacity: parent.pressed ? 0.75 : 1
            }
        }
    }

    component Field: Column {
        id: field
        property alias label: cap.text
        property alias text: input.text
        property alias placeholder: input.placeholderText
        property alias input: input
        width: parent ? parent.width : 300
        spacing: 6
        Label {
            id: cap
            color: theme.textDim
            font.pixelSize: 13
        }
        TextField {
            id: input
            width: parent.width
            height: 48
            color: theme.text
            placeholderTextColor: theme.textFaint
            font.pixelSize: 16
            leftPadding: 14
            rightPadding: 14
            inputMethodHints: Qt.ImhNoPredictiveText
            onTextEdited: error.text = ""
            background: Rectangle {
                radius: 10
                color: theme.surface
                border.width: input.activeFocus ? 2 : 0
                border.color: theme.accent
            }
        }
    }

    Flickable {
        anchors.fill: parent
        contentHeight: form.implicitHeight + 40
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: form
            x: 20
            y: 8
            width: parent.width - 40
            spacing: 16

            Field {
                id: nameField
                objectName: "nameField"
                label: qsTr("Name")
                placeholder: qsTr("Ghostty")
                text: page.item.name || ""
            }
            Field {
                id: groupField
                label: qsTr("Category")
                placeholder: qsTr("iPhone, Gaming, PC…")
                text: page.item.group || ""
            }
            Flow {  // tap an existing category instead of typing it
                width: parent.width
                spacing: 8
                visible: fleet.groups.length > 0
                Repeater {
                    model: fleet.groups.filter(g => g !== "Other")
                    Chip {
                        required property string modelData
                        text: modelData
                        selected: groupField.text === modelData
                        onClicked: groupField.text = modelData
                    }
                }
            }
            Field {
                id: platformField
                label: qsTr("Platform")
                placeholder: qsTr("Linux, iOS, Steam…")
                text: page.item.platform || ""
            }

            Column {  // source: opens a sheet of every checker
                width: parent.width
                spacing: 6
                Label {
                    text: qsTr("Checked via")
                    color: theme.textDim
                    font.pixelSize: 13
                }
                ItemDelegate {
                    objectName: "sourcePicker"
                    width: parent.width
                    height: 48
                    focusPolicy: Qt.NoFocus
                    onClicked: sourceSheet.open()
                    background: Rectangle { radius: 10; color: theme.surface }
                    contentItem: Item {
                        Label {
                            anchors.left: parent.left
                            anchors.leftMargin: 2
                            anchors.right: chevron.left
                            anchors.verticalCenter: parent.verticalCenter
                            text: page.source.label || page.kind
                            color: theme.text
                            font.pixelSize: 16
                            elide: Text.ElideRight
                        }
                        Icon {
                            id: chevron
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            name: "chevron_down"
                            tint: theme.textDim
                            size: 20
                        }
                    }
                }
            }
            Field {
                id: refField
                objectName: "refField"
                visible: page.kind !== "manual"
                label: qsTr("Handle")
                placeholder: page.source.hint || ""
                text: page.item.ref || ""
                input.inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase | Qt.ImhUrlCharactersOnly
            }
            Field {
                id: installedField
                label: qsTr("Version you have")
                placeholder: qsTr("optional")
                text: page.item.installed || ""
                input.inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
            }
            Field {
                id: changelogField
                label: qsTr("Changelog link")
                placeholder: qsTr("optional — {version} fills in the latest")
                text: page.item.ownChangelogUrl || ""
                input.inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoAutoUppercase
            }

            Label {
                id: error
                objectName: "formError"
                width: parent.width
                visible: text !== ""
                color: theme.warning
                font.pixelSize: 14
                wrapMode: Text.Wrap
            }

            PillButton {
                objectName: "deleteItem"
                visible: page.original !== ""
                width: parent.width
                iconName: "trash"
                tint: theme.warning
                text: qsTr("Stop tracking")
                onClicked: confirmDelete.open()
            }
        }
    }

    Sheet {
        id: sourceSheet
        objectName: "sourceSheet"
        Repeater {
            model: page.sourceList
            ItemDelegate {
                required property var modelData
                width: parent ? parent.width : 300
                height: 52
                focusPolicy: Qt.NoFocus
                onClicked: {
                    page.kind = modelData.kind
                    error.text = ""
                    sourceSheet.close()
                }
                background: Rectangle { radius: 10; color: theme.text; opacity: parent.pressed ? 0.08 : 0 }
                contentItem: Label {
                    text: modelData.label
                    color: modelData.kind === page.kind ? theme.accent : theme.text
                    font.pixelSize: 16
                    font.weight: modelData.kind === page.kind ? Font.DemiBold : Font.Normal
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }
        }
    }

    Sheet {
        id: confirmDelete
        Label {
            width: parent.width
            text: qsTr("Stop tracking %1?").arg(page.original)
            color: theme.text
            font.pixelSize: 18
            font.weight: Font.DemiBold
            wrapMode: Text.Wrap
        }
        PillButton {
            objectName: "confirmDelete"
            width: parent.width
            iconName: "trash"
            tint: theme.warning
            text: qsTr("Stop tracking")
            onClicked: {
                fleet.remove(page.original)
                confirmDelete.close()
                page.done()
            }
        }
        PillButton {
            width: parent.width
            text: qsTr("Keep it")
            onClicked: confirmDelete.close()
        }
    }
}
