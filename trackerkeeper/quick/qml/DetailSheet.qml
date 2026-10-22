// Everything about one item, and every action on it, in a bottom sheet:
// what you have → what's out, when, where from, what changed, and big
// buttons for the three things you'd do about it.
import QtQuick
import QtQuick.Controls

Sheet {
    id: sheet
    objectName: "detailSheet"
    property var item: ({})

    signal edit(string name)

    function show(name) {
        item = fleet.item(name)
        open()
    }

    Label {
        width: parent.width
        text: sheet.item.name || ""
        color: theme.text
        font.pixelSize: 22
        font.weight: Font.DemiBold
        wrapMode: Text.Wrap
    }
    Label {  // provenance: category · channel · age · checked
        width: parent.width
        topPadding: -6
        text: [sheet.item.group, sheet.item.platform, sheet.item.channel, sheet.item.age]
              .filter(s => s).join("  ·  ")
        color: theme.textDim
        font.pixelSize: 14
        wrapMode: Text.Wrap
    }

    // the headline: before → after, or what you're on
    Flow {
        width: parent.width
        spacing: 10
        Label {
            visible: !!sheet.item.hasUpdate
            text: sheet.item.installed || "—"
            color: theme.textDim
            font.pixelSize: 18
        }
        Label {
            visible: !!sheet.item.hasUpdate
            text: "→"
            color: theme.textDim
            font.pixelSize: 18
        }
        Label {
            text: sheet.item.latest || sheet.item.installed || qsTr("not checked yet")
            color: sheet.item.isNew ? theme.accent : theme.text
            font.pixelSize: 18
            font.weight: Font.DemiBold
        }
        Label {
            visible: !sheet.item.hasUpdate && !!sheet.item.latest
            text: qsTr("current")
            color: theme.textDim
            font.pixelSize: 18
        }
    }

    Label {
        visible: !!sheet.item.error
        width: parent.width
        text: sheet.item.error || ""
        color: theme.warning
        font.pixelSize: 14
        wrapMode: Text.Wrap
    }

    PillButton {
        objectName: "openChangelog"
        visible: !!sheet.item.changelogUrl
        width: parent.width
        filled: true
        iconName: "external"
        text: qsTr("Open changelog")
        onClicked: Qt.openUrlExternally(sheet.item.changelogUrl)
    }
    Row {
        width: parent.width
        spacing: 10
        PillButton {
            objectName: "markUpdated"
            visible: !!sheet.item.hasUpdate
            width: (parent.width - parent.spacing) / 2
            iconName: "check"
            text: qsTr("Mark updated")
            onClicked: {
                fleet.markUpdated(sheet.item.name)
                sheet.close()
            }
        }
        PillButton {
            objectName: "editItem"
            width: sheet.item.hasUpdate ? (parent.width - parent.spacing) / 2 : parent.width
            iconName: "edit"
            text: qsTr("Edit")
            onClicked: {
                sheet.close()
                sheet.edit(sheet.item.name)
            }
        }
    }

    // what changed — plain text from the source, never rich text
    Label {
        visible: !!sheet.item.notes
        width: parent.width
        topPadding: 6
        text: qsTr("WHAT'S NEW")
        color: theme.textDim
        font.pixelSize: 12
        font.weight: Font.DemiBold
        font.letterSpacing: 1
    }
    Label {
        visible: !!sheet.item.notes
        width: parent.width
        text: sheet.item.notes || ""
        textFormat: Text.PlainText
        color: theme.text
        font.pixelSize: 14
        lineHeight: 1.25
        wrapMode: Text.Wrap
    }
    Label {
        visible: !!sheet.item.checked
        width: parent.width
        text: qsTr("checked %1").arg(sheet.item.checked || "")
        color: theme.textFaint
        font.pixelSize: 12
    }
}
