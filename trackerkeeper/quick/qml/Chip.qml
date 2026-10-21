// A filter chip. `selected` fills it with the accent; `count` trails the label.
import QtQuick
import QtQuick.Controls

AbstractButton {
    id: chip
    property bool selected: false
    property int count: 0
    focusPolicy: Qt.NoFocus
    hoverEnabled: false
    implicitHeight: 36
    implicitWidth: row.implicitWidth + 28
    background: Rectangle {
        radius: height / 2
        color: chip.selected ? theme.accent : "transparent"
        border.width: chip.selected ? 0 : 1
        border.color: theme.textFaint
        opacity: chip.pressed ? 0.75 : 1
    }
    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 6
            Label {
                anchors.verticalCenter: parent.verticalCenter
                text: chip.text
                color: chip.selected ? theme.onAccent : theme.text
                font.pixelSize: 14
                font.weight: chip.selected ? Font.DemiBold : Font.Normal
            }
            Label {
                anchors.verticalCenter: parent.verticalCenter
                visible: chip.count > 0
                text: chip.count
                color: chip.selected ? theme.onAccent : theme.accent
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
        }
    }
}
