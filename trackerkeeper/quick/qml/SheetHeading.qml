// A small-caps heading inside a bottom sheet.
import QtQuick
import QtQuick.Controls

Label {
    width: parent ? parent.width : 300
    leftPadding: 4
    topPadding: 4
    color: theme.textFaint
    font.pixelSize: 12
    font.weight: Font.DemiBold
    font.letterSpacing: 1.2
}
